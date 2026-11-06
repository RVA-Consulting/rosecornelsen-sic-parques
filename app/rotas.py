import re
from datetime import date, datetime
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from .busca import buscar_documentos
from .catalogo import (
    ALERTA_DIAS, AREA_PILOTO, AREAS, ASSUNTOS, CHECKLIST, CONCESSIONARIAS, ETAPAS_COM_TECNICO,
    MODELO_POR_ASSUNTO, MODELOS_RESPOSTA, PARQUES, PRAZOS_COBRANCA, PRAZOS_CONCESSIONARIA,
    PRORROGACAO_DIAS, TIPOS_DOCUMENTO,
)
from .models import (
    Documento, Minuta, Pedido, PedidoConcessionaria, Usuario, db, registrar_evento, somar_dias_uteis,
)

rotas = Blueprint("rotas", __name__)

DEVOLVER_OUVIDORIA = "Outra área (devolver à Ouvidoria)"


def exige_perfil(*perfis):
    """Só deixa entrar quem tem um dos perfis indicados."""

    def decorador(view):
        @wraps(view)
        @login_required
        def protegida(*args, **kwargs):
            if current_user.perfil not in perfis:
                abort(403)
            return view(*args, **kwargs)

        return protegida

    return decorador


# ---------- Login ----------

@rotas.route("/entrar", methods=["GET", "POST"])
def entrar():
    if current_user.is_authenticated:
        return redirect(url_for("rotas.painel"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        usuario = Usuario.query.filter_by(email=email).first()
        if usuario and usuario.confere_senha(request.form.get("senha", "")):
            login_user(usuario)
            return redirect(request.args.get("next") or url_for("rotas.painel"))
        flash("E-mail ou senha incorretos.", "erro")
    return render_template("entrar.html")


@rotas.route("/sair", methods=["POST"])
def sair():
    logout_user()
    return redirect(url_for("rotas.entrar"))


# ---------- 1 · Painel de prazos ----------

@rotas.route("/")
@login_required
def painel():
    padrao = {"ouvidoria": "todas", "gerente": "parques", "tecnico": "meus"}[current_user.perfil]
    filtro = request.args.get("area", padrao)
    em_andamento = Pedido.query.filter(Pedido.etapa != "concluido")
    if filtro == "parques":
        em_andamento = em_andamento.filter(Pedido.area == AREA_PILOTO)
    elif filtro == "meus":
        em_andamento = em_andamento.filter(Pedido.responsavel_id == current_user.id)
    pedidos = sorted(em_andamento.all(), key=lambda p: p.prazo)

    na_concessionaria = [p for p in pedidos if p.etapa == "concessionaria"]
    resumo = {
        "andamento": len(pedidos),
        "parques": sum(1 for p in pedidos if p.area == AREA_PILOTO),
        "alerta": sum(1 for p in pedidos if p.situacao == "alerta"),
        "vencidos": sum(1 for p in pedidos if p.situacao == "vencido"),
        "concessionaria": len(na_concessionaria),
        "concessionaria_vencidos": sum(
            1 for p in na_concessionaria
            if p.pedido_concessionaria_aberto and p.pedido_concessionaria_aberto.situacao == "vencido"
        ),
    }
    return render_template("painel.html", pedidos=pedidos, resumo=resumo, filtro=filtro, alerta_dias=ALERTA_DIAS)


# ---------- 2 · Registro na Ouvidoria ----------

def _ler_formulario_registro(pedido=None):
    """Lê e confere os campos do formulário de registro. Devolve (dados, erros).

    Se `pedido` for informado (reclassificação), protocolo, data e texto vêm dele:
    são dados do Fala.SP e não mudam.
    """
    f = request.form
    dados = {
        "protocolo": f.get("protocolo", "").strip(),
        "data_registro": f.get("data_registro", ""),
        "texto": f.get("texto", "").strip(),
        "area": f.get("area"),
        "assunto": f.get("assunto"),
        "parque": f.get("parque") or None,
        "seguro": f.get("seguro", "sim"),
    }
    if pedido:
        dados.update(protocolo=pedido.protocolo, data_registro=pedido.data_registro.isoformat(), texto=pedido.texto)
    erros = []
    if not dados["protocolo"]:
        erros.append("Informe o protocolo do Fala.SP.")
    try:
        dados["data_registro"] = date.fromisoformat(dados["data_registro"])
        if dados["data_registro"] > date.today():
            erros.append("A data de registro não pode ser no futuro.")
    except ValueError:
        erros.append("Informe a data de registro.")
    if not dados["texto"]:
        erros.append("Copie o texto do pedido do cidadão.")
    if dados["area"] not in AREAS:
        erros.append("Escolha a área responsável.")
    if dados["assunto"] not in ASSUNTOS:
        erros.append("Escolha o assunto.")
    if dados["area"] == AREA_PILOTO and dados["parque"] not in PARQUES:
        erros.append("Escolha o parque.")
    return dados, erros


def _encaminhar(pedido, dados):
    """Aplica a classificação e decide se o pedido vai para a fila ou para validação do gerente."""
    pedido.area = dados["area"]
    pedido.assunto = dados["assunto"]
    pedido.parque = dados["parque"] if dados["area"] == AREA_PILOTO else None
    if dados["area"] == AREA_PILOTO and dados["seguro"] == "nao":
        pedido.etapa = "validar"
        registrar_evento(pedido, "Assunto marcado como novo ou sensível: aguarda validação do gerente", current_user)
    else:
        pedido.etapa = "fila"
        registrar_evento(pedido, f"Encaminhado à {pedido.area} pela Ouvidoria", current_user)


@rotas.route("/registrar", methods=["GET", "POST"])
@exige_perfil("ouvidoria")
def registrar():
    dados = {"data_registro": date.today(), "area": AREA_PILOTO, "seguro": "sim"}
    if request.method == "POST":
        dados, erros = _ler_formulario_registro()
        if dados["protocolo"] and Pedido.query.filter(
            func.lower(Pedido.protocolo) == dados["protocolo"].lower()
        ).first():
            erros.append(f"O protocolo {dados['protocolo']} já foi registrado.")
        if not erros:
            pedido = Pedido(protocolo=dados["protocolo"], data_registro=dados["data_registro"], texto=dados["texto"])
            db.session.add(pedido)
            registrar_evento(pedido, "Registrado pela Ouvidoria", current_user)
            _encaminhar(pedido, dados)
            db.session.commit()
            flash(f"{pedido.protocolo} registrado. Prazo LAI: {pedido.prazo:%d/%m/%Y}.", "ok")
            return redirect(url_for("rotas.painel"))
        for e in erros:
            flash(e, "erro")
    return render_template("registro.html", dados=dados, pedido=None, areas=AREAS, assuntos=ASSUNTOS, parques=PARQUES)


@rotas.route("/pedidos/<int:pedido_id>/reclassificar", methods=["GET", "POST"])
@exige_perfil("ouvidoria")
def reclassificar(pedido_id):
    """Pedido devolvido pelo gerente: a Ouvidoria corrige a área ou o assunto e encaminha de novo."""
    pedido = db.get_or_404(Pedido, pedido_id)
    if pedido.etapa != "reclassificar":
        abort(404)
    dados = {
        "protocolo": pedido.protocolo, "data_registro": pedido.data_registro, "texto": pedido.texto,
        "area": pedido.area, "assunto": pedido.assunto, "parque": pedido.parque, "seguro": "sim",
    }
    if request.method == "POST":
        novos, erros = _ler_formulario_registro(pedido)
        if not erros:
            _encaminhar(pedido, novos)
            db.session.commit()
            flash(f"{pedido.protocolo} encaminhado de novo.", "ok")
            return redirect(url_for("rotas.painel"))
        dados = novos
        for e in erros:
            flash(e, "erro")
    return render_template("registro.html", dados=dados, pedido=pedido, areas=AREAS, assuntos=ASSUNTOS, parques=PARQUES)


# ---------- 3 · Fila da Gerência ----------

def _carga_tecnicos():
    """Para cada técnico: quantos pedidos tem em curso e qual o mais próximo de vencer."""
    tecnicos = Usuario.query.filter_by(perfil="tecnico").order_by(Usuario.nome).all()
    carga = []
    for t in tecnicos:
        pedidos = Pedido.query.filter(Pedido.responsavel_id == t.id, Pedido.etapa.in_(ETAPAS_COM_TECNICO)).all()
        mais_urgente = min(pedidos, key=lambda p: p.prazo) if pedidos else None
        carga.append({
            "tecnico": t,
            "total": len(pedidos),
            "mais_urgente": mais_urgente,
            "na_concessionaria": sum(1 for p in pedidos if p.etapa == "concessionaria"),
        })
    maior = max((c["total"] for c in carga), default=0) or 1
    for c in carga:
        c["percentual"] = round(100 * c["total"] / maior)
    return carga


@rotas.route("/fila")
@exige_perfil("gerente")
def fila():
    base = Pedido.query.filter(Pedido.area == AREA_PILOTO)
    a_validar = sorted(base.filter(Pedido.etapa == "validar").all(), key=lambda p: p.prazo)
    a_distribuir = sorted(base.filter(Pedido.etapa == "fila").all(), key=lambda p: p.prazo)
    return render_template(
        "fila.html", a_validar=a_validar, a_distribuir=a_distribuir, carga=_carga_tecnicos(),
        assuntos=ASSUNTOS, parques=PARQUES, devolver=DEVOLVER_OUVIDORIA,
    )


@rotas.route("/pedidos/<int:pedido_id>/validar", methods=["POST"])
@exige_perfil("gerente")
def validar(pedido_id):
    pedido = db.get_or_404(Pedido, pedido_id)
    if pedido.etapa != "validar":
        abort(404)
    assunto = request.form.get("assunto")
    if assunto == DEVOLVER_OUVIDORIA:
        pedido.etapa = "reclassificar"
        registrar_evento(pedido, "Devolvido à Ouvidoria pelo gerente: assunto de outra área", current_user)
        flash(f"{pedido.protocolo} devolvido à Ouvidoria.", "ok")
    elif assunto in ASSUNTOS and request.form.get("parque") in PARQUES:
        pedido.assunto, pedido.parque, pedido.etapa = assunto, request.form["parque"], "fila"
        registrar_evento(pedido, f"Classificação confirmada pelo gerente: {assunto} · {pedido.parque}", current_user)
        flash(f"Classificação de {pedido.protocolo} confirmada. Agora ele está na lista para distribuir.", "ok")
    else:
        flash("Escolha o assunto e o parque.", "erro")
    db.session.commit()
    return redirect(url_for("rotas.fila"))


@rotas.route("/pedidos/<int:pedido_id>/distribuir", methods=["POST"])
@exige_perfil("gerente")
def distribuir(pedido_id):
    pedido = db.get_or_404(Pedido, pedido_id)
    if pedido.etapa != "fila":
        abort(404)
    tecnico = db.session.get(Usuario, request.form.get("tecnico", type=int) or 0)
    if not tecnico or tecnico.perfil != "tecnico":
        flash("Escolha um técnico.", "erro")
        return redirect(url_for("rotas.fila"))
    pedido.responsavel, pedido.etapa = tecnico, "analise"
    registrar_evento(pedido, f"Distribuído a {tecnico.nome} pelo gerente", current_user)
    db.session.commit()
    flash(f"{pedido.protocolo} distribuído a {tecnico.nome.rstrip('.')}.", "ok")
    return redirect(url_for("rotas.fila"))


# ---------- Detalhe do pedido (histórico) ----------

@rotas.app_template_global()
def link_do_pedido(p):
    """Para onde o protocolo leva, conforme a etapa e o perfil de quem está vendo."""
    perfil = current_user.perfil
    if p.etapa in ("validar", "fila") and p.area == AREA_PILOTO and perfil == "gerente":
        return url_for("rotas.fila")
    if p.etapa == "reclassificar" and perfil == "ouvidoria":
        return url_for("rotas.reclassificar", pedido_id=p.id)
    if p.etapa == "analise" and perfil != "ouvidoria":
        return url_for("rotas.analise", pedido_id=p.id)
    if p.etapa == "concessionaria" and perfil != "ouvidoria":
        return url_for("rotas.concessionaria", pedido_id=p.id)
    if p.etapa == "minuta" and perfil != "ouvidoria":
        return url_for("rotas.minuta", pedido_id=p.id)
    if p.etapa == "aprovacao" and perfil == "gerente":
        return url_for("rotas.aprovacao", pedido_id=p.id)
    if p.etapa == "envio" and perfil != "ouvidoria":
        return url_for("rotas.envio", pedido_id=p.id)
    return url_for("rotas.pedido", pedido_id=p.id)


@rotas.route("/pedidos/<int:pedido_id>")
@login_required
def pedido(pedido_id):
    return render_template("pedido.html", pedido=db.get_or_404(Pedido, pedido_id))


def _pedido_para_atuar(pedido_id, etapa):
    """Carrega o pedido e confere se quem está logado pode trabalhar nele nesta etapa.

    Pode atuar o técnico responsável e o gerente (que supervisiona a equipe).
    """
    pedido = db.get_or_404(Pedido, pedido_id)
    if pedido.etapa != etapa:
        abort(404)
    if current_user.perfil == "ouvidoria" or (
        current_user.perfil == "tecnico" and pedido.responsavel_id != current_user.id
    ):
        abort(403)
    return pedido


# ---------- 4 · Análise do técnico ----------

def _indicador_concessionaria():
    """Quantos pedidos já analisados precisaram de informações da concessionária."""
    analisados = Pedido.query.filter(Pedido.etapa.in_(["concessionaria", "minuta", "aprovacao", "envio", "concluido"])).all()
    com_concessionaria = sum(1 for p in analisados if p.pedidos_concessionaria)
    return com_concessionaria, len(analisados)


@rotas.route("/pedidos/<int:pedido_id>/analise")
@login_required
def analise(pedido_id):
    pedido = _pedido_para_atuar(pedido_id, "analise")
    termo = request.args.get("q", "").strip()
    if termo:
        documentos = buscar_documentos(termo, pedido.parque, limite=9)
    else:
        # Sem busca: mostra o que é do parque do pedido e o que vale para todos
        documentos = [d for d in buscar_documentos("", pedido.parque) if d.parque in (pedido.parque, None)][:6]
    com, total = _indicador_concessionaria()
    return render_template(
        "analise.html", pedido=pedido, termo=termo, documentos=documentos, indicador=(com, total)
    )


@rotas.route("/pedidos/<int:pedido_id>/analise/concluir", methods=["POST"])
@login_required
def concluir_analise(pedido_id):
    pedido = _pedido_para_atuar(pedido_id, "analise")
    observacao = request.form.get("observacao", "").strip()
    complemento = f" · {observacao}" if observacao else ""
    if request.form.get("precisa") == "sim":
        return redirect(url_for("rotas.concessionaria", pedido_id=pedido.id, obs=observacao or None))
    pedido.etapa = "minuta"
    registrar_evento(pedido, f"Análise concluída: não precisa de informações da concessionária{complemento}", current_user)
    db.session.commit()
    flash(f"Análise de {pedido.protocolo} concluída. O pedido segue para a minuta da resposta.", "ok")
    return redirect(url_for("rotas.painel"))


# ---------- 5 · Pedido à concessionária ----------

def _texto_padrao(pedido, prazo):
    return (
        f"Em atendimento ao pedido de informação {pedido.protocolo}, registrado no Fala.SP em "
        f"{pedido.data_registro:%d/%m/%Y}, solicitamos o envio, até {prazo:%d/%m/%Y}, das informações abaixo:\n\n"
        f"[descreva o que precisa: documento, dado ou situação]\n\n"
        f"Assunto: {pedido.assunto} · Parque {pedido.parque}\n\n"
        f"Gerência de Parques · Arsesp"
    )


@rotas.route("/pedidos/<int:pedido_id>/concessionaria", methods=["GET", "POST"])
@login_required
def concessionaria(pedido_id):
    pedido = db.get_or_404(Pedido, pedido_id)
    hoje = date.today()

    # Já enviado: tela de acompanhamento
    if pedido.etapa == "concessionaria":
        _pedido_para_atuar(pedido_id, "concessionaria")
        return render_template(
            "concessionaria.html", pedido=pedido, pc=pedido.pedido_concessionaria_aberto, hoje=hoje,
            prazos_cobranca=[(d, somar_dias_uteis(hoje, d)) for d in PRAZOS_COBRANCA],
            prorrogacao_dias=PRORROGACAO_DIAS,
        )

    # Ainda na análise: formulário do pedido padrão
    _pedido_para_atuar(pedido_id, "analise")
    opcoes = [(d, somar_dias_uteis(hoje, d)) for d in PRAZOS_CONCESSIONARIA]
    if request.method == "POST":
        dias = request.form.get("prazo_dias", type=int)
        texto = request.form.get("texto", "").strip()
        if dias not in PRAZOS_CONCESSIONARIA or not texto:
            flash("Escolha o prazo e escreva o texto do pedido.", "erro")
        elif "[descreva" in texto:
            flash("Troque o trecho entre colchetes pelo que você precisa da concessionária.", "erro")
        else:
            pc = PedidoConcessionaria(
                pedido=pedido, destinatario=CONCESSIONARIAS.get(pedido.parque, "Concessionária"),
                texto=texto, enviado_em=hoje, prazo=somar_dias_uteis(hoje, dias),
            )
            db.session.add(pc)
            pedido.etapa = "concessionaria"
            obs = request.form.get("observacao", "").strip()
            registrar_evento(pedido, "Análise concluída: precisa de informações da concessionária" + (f" · {obs}" if obs else ""), current_user)
            registrar_evento(pedido, f"Pedido padrão enviado à concessionária, prazo {pc.prazo:%d/%m}", current_user)
            db.session.commit()
            flash(f"Pedido à concessionária registrado. Prazo de resposta: {pc.prazo:%d/%m/%Y}.", "ok")
            return redirect(url_for("rotas.concessionaria", pedido_id=pedido.id))
    texto = request.form.get("texto") or _texto_padrao(pedido, opcoes[0][1])
    return render_template(
        "concessionaria_novo.html", pedido=pedido, opcoes=opcoes, texto=texto,
        destinatario=CONCESSIONARIAS.get(pedido.parque, "Concessionária"),
        observacao=request.values.get("obs") or request.form.get("observacao", ""),
    )


@rotas.route("/pedidos/<int:pedido_id>/concessionaria/resposta", methods=["POST"])
@login_required
def resposta_concessionaria(pedido_id):
    pedido = _pedido_para_atuar(pedido_id, "concessionaria")
    pc = pedido.pedido_concessionaria_aberto
    resumo = request.form.get("resposta", "").strip()
    try:
        recebido = date.fromisoformat(request.form.get("recebido_em", ""))
    except ValueError:
        recebido = None
    if not resumo or not recebido or recebido > date.today() or recebido < pc.enviado_em:
        flash("Informe a data em que a resposta chegou (entre o envio e hoje) e o que a concessionária respondeu.", "erro")
        return redirect(url_for("rotas.concessionaria", pedido_id=pedido.id))
    pc.respondido_em, pc.resposta = recebido, resumo
    pedido.etapa = "minuta"
    registrar_evento(pedido, f"Informações da concessionária recebidas em {recebido:%d/%m}", current_user)
    db.session.commit()
    flash(f"Resposta da concessionária registrada. {pedido.protocolo} segue para a minuta.", "ok")
    return redirect(url_for("rotas.painel"))


@rotas.route("/pedidos/<int:pedido_id>/concessionaria/cobrar", methods=["POST"])
@login_required
def cobrar_concessionaria(pedido_id):
    pedido = _pedido_para_atuar(pedido_id, "concessionaria")
    pc = pedido.pedido_concessionaria_aberto
    dias = request.form.get("prazo_dias", type=int)
    if dias not in PRAZOS_COBRANCA:
        flash("Escolha o novo prazo.", "erro")
        return redirect(url_for("rotas.concessionaria", pedido_id=pedido.id))
    pc.cobrancas += 1
    pc.prazo = somar_dias_uteis(date.today(), dias)
    registrar_evento(pedido, f"Concessionária cobrada ({pc.cobrancas}ª vez), novo prazo {pc.prazo:%d/%m}", current_user)
    db.session.commit()
    flash(f"Cobrança registrada. Novo prazo da concessionária: {pc.prazo:%d/%m/%Y}.", "ok")
    return redirect(url_for("rotas.concessionaria", pedido_id=pedido.id))


@rotas.route("/pedidos/<int:pedido_id>/prorrogar", methods=["POST"])
@login_required
def prorrogar(pedido_id):
    """Prorroga o prazo da LAI por mais 10 dias. A justificativa também precisa ir ao cidadão pelo Fala.SP."""
    pedido = db.get_or_404(Pedido, pedido_id)
    _pedido_para_atuar(pedido_id, pedido.etapa)
    justificativa = request.form.get("justificativa", "").strip()
    if pedido.prorrogado:
        flash("Este pedido já foi prorrogado. A LAI só permite uma prorrogação.", "erro")
    elif pedido.dias_restantes < 0:
        flash("O prazo da LAI já venceu: a prorrogação precisa ser feita antes do vencimento.", "erro")
    elif not justificativa:
        flash("Escreva a justificativa da prorrogação.", "erro")
    else:
        pedido.prorrogado = True
        registrar_evento(pedido, f"Prazo LAI prorrogado por {PRORROGACAO_DIAS} dias até {pedido.prazo:%d/%m} · {justificativa}", current_user)
        db.session.commit()
        flash(f"Prazo prorrogado até {pedido.prazo:%d/%m/%Y}. Lembre de registrar a justificativa no Fala.SP.", "ok")
    return redirect(link_do_pedido(pedido))


# ---------- 6 · Minuta da resposta ----------

# Trecho entre colchetes que o modelo pede para trocar, ex.: "[explique o motivo]"
TRECHO_A_PREENCHER = re.compile(r"\[[^\]\n]{3,}\]")


def _modelos_preenchidos(pedido):
    return {
        nome: texto.format(protocolo=pedido.protocolo, parque=pedido.parque or "")
        for nome, texto in MODELOS_RESPOSTA.items()
    }


@rotas.route("/pedidos/<int:pedido_id>/minuta", methods=["GET", "POST"])
@login_required
def minuta(pedido_id):
    pedido = _pedido_para_atuar(pedido_id, "minuta")
    modelos = _modelos_preenchidos(pedido)
    m = pedido.minuta
    if not m:
        sugerido = MODELO_POR_ASSUNTO.get(pedido.assunto, "Em branco")
        # Ainda não ligada ao pedido: só é gravada quando o técnico salvar
        m = Minuta(modelo=sugerido, texto=modelos[sugerido], checklist=[], devolucoes=0)

    if request.method == "POST":
        acao = request.form.get("acao")
        modelo = request.form.get("modelo")
        m.modelo = modelo if modelo in MODELOS_RESPOSTA else None
        m.texto = request.form.get("texto", "").strip()
        m.checklist = [c for c in request.form.getlist("checklist") if c in CHECKLIST]
        m.autor = current_user
        m.pedido = pedido
        db.session.add(m)

        erro = None
        if acao in ("aprovacao", "padrao"):
            if not m.texto:
                erro = "Escreva a resposta ao cidadão."
            elif TRECHO_A_PREENCHER.search(m.texto):
                erro = "Ainda há trechos entre colchetes para trocar no texto."
            elif acao == "padrao" and (not m.modelo or m.modelo == "Em branco"):
                erro = "Resposta-padrão precisa partir de um modelo já validado. Envie para aprovação."
            elif acao == "padrao" and not m.checklist_completo:
                erro = "Para seguir como resposta-padrão, todos os itens do checklist precisam estar marcados."

        if erro:
            flash(erro + " O rascunho foi salvo.", "erro")
        elif acao == "aprovacao":
            pendentes = len(CHECKLIST) - len(m.checklist)
            m.resposta_padrao, m.enviada_em, m.motivo_devolucao = False, datetime.now(), None
            pedido.etapa = "aprovacao"
            aviso = f" ({pendentes} {'item' if pendentes == 1 else 'itens'} do checklist pendente{'s' if pendentes > 1 else ''})" if pendentes else ""
            registrar_evento(pedido, f"Minuta enviada para aprovação{aviso}", current_user)
        elif acao == "padrao":
            m.resposta_padrao, m.enviada_em, m.motivo_devolucao = True, datetime.now(), None
            pedido.etapa = "envio"
            registrar_evento(pedido, f"Resposta-padrão ({m.modelo}): segue direto para envio, na alçada do técnico", current_user)
        db.session.commit()

        if erro or acao not in ("aprovacao", "padrao"):
            if not erro:
                flash("Rascunho salvo.", "ok")
            return redirect(url_for("rotas.minuta", pedido_id=pedido.id))
        if acao == "aprovacao":
            flash(f"Minuta de {pedido.protocolo} enviada para aprovação do gerente.", "ok")
            return redirect(url_for("rotas.painel"))
        flash("Resposta-padrão pronta. Falta registrar no Fala.SP.", "ok")
        return redirect(url_for("rotas.envio", pedido_id=pedido.id))

    return render_template(
        "minuta.html", pedido=pedido, m=m, modelos=modelos, checklist=CHECKLIST,
        respostas_concessionaria=[pc for pc in pedido.pedidos_concessionaria if pc.respondido_em],
    )


# ---------- 7 · Aprovação do gerente ----------

@rotas.route("/pedidos/<int:pedido_id>/aprovacao", methods=["GET", "POST"])
@exige_perfil("gerente")
def aprovacao(pedido_id):
    pedido = _pedido_para_atuar(pedido_id, "aprovacao")
    m = pedido.minuta
    if request.method == "POST":
        if request.form.get("decisao") == "aprovar":
            m.aprovada_por, m.aprovada_em = current_user, datetime.now()
            pedido.etapa = "envio"
            registrar_evento(pedido, "Aprovada pelo gerente", current_user)
            db.session.commit()
            flash(f"Resposta de {pedido.protocolo} aprovada. O técnico já pode registrar no Fala.SP.", "ok")
            return redirect(url_for("rotas.painel"))
        motivo = request.form.get("motivo", "").strip()
        if not motivo:
            flash("Para devolver, escreva o motivo.", "erro")
        else:
            m.devolucoes += 1
            m.motivo_devolucao = motivo
            pedido.etapa = "minuta"
            registrar_evento(pedido, f"Devolvida ao técnico · {motivo}", current_user)
            db.session.commit()
            flash(f"Minuta devolvida a {m.autor.nome.rstrip('.') if m.autor else 'o técnico'}.", "ok")
            return redirect(url_for("rotas.painel"))
    return render_template(
        "aprovacao.html", pedido=pedido, m=m, checklist=CHECKLIST,
        respostas_concessionaria=[pc for pc in pedido.pedidos_concessionaria if pc.respondido_em],
    )


# ---------- 8 · Envio e baixa do prazo ----------

@rotas.route("/pedidos/<int:pedido_id>/envio", methods=["GET", "POST"])
@login_required
def envio(pedido_id):
    pedido = _pedido_para_atuar(pedido_id, "envio")
    m = pedido.minuta
    if request.method == "POST":
        if not request.form.get("confirmo"):
            flash("Marque a confirmação de que a resposta foi registrada no Fala.SP.", "erro")
            return redirect(url_for("rotas.envio", pedido_id=pedido.id))
        m.registrada_falasp_em = datetime.now()
        pedido.etapa = "concluido"
        registrar_evento(pedido, "Resposta registrada no Fala.SP e prazo baixado", current_user)
        if request.form.get("incluir_base"):
            # A resposta aprovada vira modelo para os próximos pedidos parecidos
            db.session.add(Documento(
                tipo="Resposta anterior", parque=pedido.parque, titulo=f"{pedido.protocolo} · {pedido.assunto}",
                resumo=("Resposta-padrão" if m.resposta_padrao else "Aprovada pelo gerente")
                + f" em {date.today():%d/%m/%Y}. Pode servir de modelo.",
                conteudo=m.texto, cadastrado_por=current_user,
            ))
        db.session.commit()
        flash(f"{pedido.protocolo} concluído dentro do prazo." if pedido.dias_restantes >= 0
              else f"{pedido.protocolo} concluído, com {-pedido.dias_restantes} dias de atraso.", "ok")
        return redirect(url_for("rotas.painel"))
    return render_template("envio.html", pedido=pedido, m=m)


# ---------- Base de conhecimento ----------

@rotas.route("/base")
@exige_perfil("tecnico", "gerente")
def base():
    termo = request.args.get("q", "").strip()
    return render_template("base_conhecimento.html", termo=termo, documentos=buscar_documentos(termo))


@rotas.route("/base/<int:doc_id>")
@exige_perfil("tecnico", "gerente")
def documento(doc_id):
    # "Voltar" só pode levar a uma página do próprio sistema
    voltar = request.args.get("voltar", "")
    if not voltar.startswith("/") or voltar.startswith("//") or "\\" in voltar:
        voltar = url_for("rotas.base")
    return render_template("documento.html", doc=db.get_or_404(Documento, doc_id), voltar=voltar)


@rotas.route("/base/novo", methods=["GET", "POST"])
@exige_perfil("tecnico", "gerente")
def novo_documento():
    dados = request.form
    if request.method == "POST":
        campos = {k: dados.get(k, "").strip() for k in ("tipo", "titulo", "resumo", "conteudo", "parque")}
        if campos["tipo"] not in TIPOS_DOCUMENTO or campos["parque"] not in PARQUES + [""]:
            flash("Escolha o tipo e o parque.", "erro")
        elif not (campos["titulo"] and campos["resumo"] and campos["conteudo"]):
            flash("Preencha título, resumo e conteúdo.", "erro")
        else:
            doc = Documento(**{**campos, "parque": campos["parque"] or None}, cadastrado_por=current_user)
            db.session.add(doc)
            db.session.commit()
            flash("Documento incluído na base de conhecimento.", "ok")
            return redirect(url_for("rotas.documento", doc_id=doc.id))
    return render_template("documento_novo.html", dados=dados, tipos=TIPOS_DOCUMENTO, parques=PARQUES)
