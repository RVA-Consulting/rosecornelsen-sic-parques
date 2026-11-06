from datetime import date, datetime, timedelta

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

from .catalogo import ALERTA_DIAS, CHECKLIST, ETAPAS, PERFIS, PRAZO_LAI_DIAS, PRORROGACAO_DIAS

db = SQLAlchemy()


class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    perfil = db.Column(db.String(20), nullable=False)  # ouvidoria | gerente | tecnico
    # Parque em que o técnico é referência (sugerido na distribuição)
    parque_referencia = db.Column(db.String(60))

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def confere_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

    @property
    def perfil_rotulo(self):
        return PERFIS[self.perfil]


class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    protocolo = db.Column(db.String(40), unique=True, nullable=False)
    data_registro = db.Column(db.Date, nullable=False)
    texto = db.Column(db.Text, nullable=False)
    area = db.Column(db.String(60), nullable=False)
    assunto = db.Column(db.String(80), nullable=False)
    parque = db.Column(db.String(60))
    etapa = db.Column(db.String(20), nullable=False)
    prorrogado = db.Column(db.Boolean, nullable=False, default=False)
    responsavel_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    responsavel = db.relationship("Usuario")
    eventos = db.relationship(
        "Evento", back_populates="pedido", order_by="Evento.data_hora", cascade="all, delete-orphan"
    )
    pedidos_concessionaria = db.relationship(
        "PedidoConcessionaria", back_populates="pedido", order_by="PedidoConcessionaria.enviado_em",
        cascade="all, delete-orphan",
    )
    minuta = db.relationship("Minuta", back_populates="pedido", uselist=False, cascade="all, delete-orphan")

    @property
    def pedido_concessionaria_aberto(self):
        """O pedido à concessionária que ainda espera resposta, se houver."""
        return next((pc for pc in self.pedidos_concessionaria if not pc.respondido_em), None)

    @staticmethod
    def calcular_prazo(data_registro):
        return data_registro + timedelta(days=PRAZO_LAI_DIAS)

    @property
    def prazo(self):
        base = self.calcular_prazo(self.data_registro)
        return base + timedelta(days=PRORROGACAO_DIAS) if self.prorrogado else base

    @property
    def dias_restantes(self):
        return (self.prazo - date.today()).days

    @property
    def situacao(self):
        """'vencido', 'alerta' ou 'ok' — define a cor do prazo no painel."""
        if self.dias_restantes < 0:
            return "vencido"
        if self.dias_restantes <= ALERTA_DIAS:
            return "alerta"
        return "ok"

    @property
    def etapa_numero(self):
        return ETAPAS[self.etapa][0]

    @property
    def etapa_rotulo(self):
        return ETAPAS[self.etapa][1]

    @property
    def responsavel_rotulo(self):
        if self.etapa == "reclassificar":
            return "Ouvidoria"
        if self.etapa in ("validar", "aprovacao"):
            return "Gerente"
        if self.etapa == "fila":
            return "A distribuir"
        return self.responsavel.nome if self.responsavel else "—"


def somar_dias_uteis(inicio, dias):
    """Soma dias úteis (segunda a sexta). Feriados ainda não são considerados."""
    d = inicio
    while dias > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            dias -= 1
    return d


class PedidoConcessionaria(db.Model):
    """Pedido de informações enviado à concessionária, com prazo controlado pelo sistema."""

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey("pedido.id"), nullable=False)
    pedido = db.relationship("Pedido", back_populates="pedidos_concessionaria")
    destinatario = db.Column(db.String(120), nullable=False)
    texto = db.Column(db.Text, nullable=False)
    enviado_em = db.Column(db.Date, nullable=False)
    prazo = db.Column(db.Date, nullable=False)
    cobrancas = db.Column(db.Integer, nullable=False, default=0)
    respondido_em = db.Column(db.Date)
    resposta = db.Column(db.Text)

    @property
    def dias_restantes(self):
        return (self.prazo - date.today()).days

    @property
    def situacao(self):
        """'respondido', 'vencido' ou 'aguardando'."""
        if self.respondido_em:
            return "respondido"
        return "vencido" if self.dias_restantes < 0 else "aguardando"


class Minuta(db.Model):
    """Resposta ao cidadão: escrita pelo técnico, aprovada pelo gerente quando não é resposta-padrão."""

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey("pedido.id"), unique=True, nullable=False)
    pedido = db.relationship("Pedido", back_populates="minuta")
    modelo = db.Column(db.String(60))
    texto = db.Column(db.Text, nullable=False, default="")
    checklist = db.Column(db.JSON, nullable=False, default=list)  # chaves de CHECKLIST marcadas
    resposta_padrao = db.Column(db.Boolean, nullable=False, default=False)
    autor_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    autor = db.relationship("Usuario", foreign_keys=[autor_id])
    enviada_em = db.Column(db.DateTime)  # quando saiu do técnico (para aprovação ou envio)
    aprovada_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    aprovada_por = db.relationship("Usuario", foreign_keys=[aprovada_por_id])
    aprovada_em = db.Column(db.DateTime)
    devolucoes = db.Column(db.Integer, nullable=False, default=0)
    motivo_devolucao = db.Column(db.Text)  # último motivo, mostrado ao técnico
    registrada_falasp_em = db.Column(db.DateTime)

    @property
    def checklist_completo(self):
        return set(CHECKLIST) <= set(self.checklist or [])


class Documento(db.Model):
    """Item da base de conhecimento: contratos, normativos e respostas já aprovadas."""

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(40), nullable=False)
    titulo = db.Column(db.String(160), nullable=False)
    resumo = db.Column(db.String(255), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    parque = db.Column(db.String(60))  # vazio = vale para todos os parques
    cadastrado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    cadastrado_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    cadastrado_por = db.relationship("Usuario")


class Evento(db.Model):
    """Histórico do pedido: cada etapa fica registrada com data e responsável."""

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey("pedido.id"), nullable=False)
    pedido = db.relationship("Pedido", back_populates="eventos")
    data_hora = db.Column(db.DateTime, nullable=False, default=datetime.now)
    descricao = db.Column(db.String(255), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    usuario = db.relationship("Usuario")


def registrar_evento(pedido, descricao, usuario, quando=None):
    db.session.add(Evento(pedido=pedido, descricao=descricao, usuario=usuario, data_hora=quando or datetime.now()))
