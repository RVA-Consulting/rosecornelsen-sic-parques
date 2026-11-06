"""Dados fictícios para testar o sistema (os mesmos casos do protótipo).

As datas são calculadas a partir de hoje, para os prazos continuarem fazendo sentido.
A senha dos usuários de teste vem da variável SEED_SENHA (veja o .env.example).
"""

import os
from datetime import date, datetime, time, timedelta

from .models import Documento, Minuta, Pedido, PedidoConcessionaria, Usuario, db, registrar_evento, somar_dias_uteis

USUARIOS = [
    ("Paula O.", "ouvidoria@teste.local", "ouvidoria", None),
    ("Marta S.", "gerente@teste.local", "gerente", None),
    ("Ana P.", "ana@teste.local", "tecnico", "Villa-Lobos"),
    ("Bruno L.", "bruno@teste.local", "tecnico", "Água Branca"),
    ("Carla M.", "carla@teste.local", "tecnico", "Cândido Portinari"),
]

# protocolo, dias desde o registro, área, assunto, parque, etapa, responsável (e-mail), texto
PEDIDOS = [
    ("SIC 2026-004812", 16, "Gerência de Parques", "Contrato · manutenção", "Villa-Lobos", "analise", "ana@teste.local",
     "Gostaria de saber quais serviços de manutenção a concessionária é obrigada a fazer no Parque Villa-Lobos e com que frequência."),
    ("SIC 2026-004790", 15, "Gerência de Parques", "Fiscalização da Arsesp", "Água Branca", "concessionaria", "bruno@teste.local",
     "Quantas fiscalizações a Arsesp fez no Parque Água Branca neste ano e quais foram os resultados?"),
    ("SIC 2026-004771", 15, "Gerência de Parques", "Contrato · tarifas", "Cândido Portinari", "aprovacao", "carla@teste.local",
     "Quais são os valores cobrados no estacionamento do Parque Cândido Portinari e quem autorizou esses valores?"),
    ("SIC 2026-004855", 8, "Gerência de Parques", "Pedido de vista de processo", "Villa-Lobos", "minuta", "carla@teste.local",
     "Solicito vista do processo de fiscalização sobre a reforma dos banheiros do Parque Villa-Lobos."),
    ("SIC 2026-004861", 6, "Gerência de Parques", "Contrato · manutenção", "Villa-Lobos", "fila", None,
     "Peço informação sobre o contrato de poda e manejo de árvores no Parque Villa-Lobos."),
    ("SIC 2026-004870", 3, "Gerência de Parques", "Contrato · obras e cronograma", "Água Branca", "fila", None,
     "Solicito cópia do cronograma de obras previsto no contrato de concessão do Parque Água Branca e informação sobre "
     "o que a Arsesp fez para acompanhar os atrasos apontados em 2026."),
    ("SIC 2026-004873", 2, "Gerência de Parques", "Fiscalização da Arsesp · penalidades", "Villa-Lobos", "validar", None,
     "Quero saber quanto a concessionária pagou de outorga ao Estado e se a Arsesp aplicou alguma multa por falta de "
     "segurança no parque."),
    ("SIC 2026-004880", 1, "Gerência de Saneamento", "Outro assunto", None, "fila", None,
     "Solicito informação sobre o reajuste da tarifa de água aprovado neste ano."),
]


# Base de conhecimento: textos fictícios só para teste (troque pelos documentos reais)
DOCUMENTOS = [
    ("Contrato", "Água Branca", "Anexo de Encargos · cronograma de investimentos",
     "Prazos das obras obrigatórias por ano de concessão.",
     "[Texto fictício para teste] O Anexo de Encargos lista as obras obrigatórias do Parque Água Branca e o ano de "
     "concessão em que cada uma deve ser concluída: reforma dos sanitários (ano 1), restauro do galpão histórico "
     "(ano 2) e recuperação dos caminhos internos (ano 3). Atrasos devem ser justificados à Arsesp."),
    ("Contrato", "Villa-Lobos", "Contrato de concessão · cláusulas de manutenção",
     "Serviços de manutenção obrigatórios e frequência mínima.",
     "[Texto fictício para teste] A concessionária deve manter limpeza diária, poda e manejo de árvores conforme "
     "plano anual aprovado, e manutenção preventiva mensal de sanitários, iluminação e equipamentos de lazer."),
    ("Normativo Arsesp", None, "Procedimento de fiscalização dos parques",
     "Como a agência registra e cobra atrasos.",
     "[Texto fictício para teste] A fiscalização registra as não conformidades em relatório, notifica a "
     "concessionária e fixa prazo para plano de recuperação. O descumprimento pode gerar penalidade."),
    ("Normativo do poder concedente", None, "Diretrizes de preços públicos nos parques",
     "Quem aprova tarifas de estacionamento e outros serviços.",
     "[Texto fictício para teste] Os valores de estacionamento e serviços cobrados nos parques seguem a tabela "
     "aprovada pelo poder concedente e são reajustados anualmente conforme o contrato."),
    ("Normativo Arsesp", None, "Regras para pedido de vista de processos",
     "Prazos e forma de dar vista de processos ao cidadão.",
     "[Texto fictício para teste] O pedido de vista é atendido com agendamento ou cópia digital, retirando "
     "informações pessoais e sigilosas antes do envio."),
    ("Resposta anterior", "Villa-Lobos", "SIC 2026-003115 · cronograma Villa-Lobos",
     "Aprovada pelo gerente. Pode servir de modelo.",
     "[Texto fictício para teste] Prezado(a) cidadão(ã), em resposta ao seu pedido, encaminhamos o cronograma das "
     "obras obrigatórias do Parque Villa-Lobos com a situação de cada item. Caso não concorde com esta resposta, é "
     "possível apresentar recurso em até 10 dias pelo Fala.SP."),
]


def popular():
    """Apaga tudo e recria os dados de teste."""
    senha = os.environ.get("SEED_SENHA")
    if not senha:
        raise SystemExit("Defina SEED_SENHA no arquivo .env antes de rodar o seed.")

    db.drop_all()
    db.create_all()

    usuarios = {}
    for nome, email, perfil, parque in USUARIOS:
        u = Usuario(nome=nome, email=email, perfil=perfil, parque_referencia=parque)
        u.definir_senha(senha)
        db.session.add(u)
        usuarios[email] = u

    ouvidoria, gerente = usuarios["ouvidoria@teste.local"], usuarios["gerente@teste.local"]
    hoje = date.today()
    for protocolo, dias, area, assunto, parque, etapa, resp, texto in PEDIDOS:
        registro = hoje - timedelta(days=dias)
        p = Pedido(protocolo=protocolo, data_registro=registro, texto=texto, area=area, assunto=assunto,
                   parque=parque, etapa=etapa, responsavel=usuarios.get(resp))
        db.session.add(p)
        quando = datetime.combine(registro, time(10, 0))
        registrar_evento(p, f"Registrado pela Ouvidoria e encaminhado à {area}", ouvidoria, quando)
        if etapa == "validar":
            registrar_evento(p, "Assunto marcado como novo ou sensível: aguarda validação do gerente", ouvidoria, quando)
        if etapa not in ("fila", "validar") and p.responsavel and p.responsavel.perfil == "tecnico":
            registrar_evento(p, f"Distribuído a {p.responsavel.nome} pelo gerente", gerente, quando + timedelta(days=1))

    # 004790: pedido à concessionária enviado há 8 dias, com prazo de 5 dias úteis já vencido
    p790 = next(p for p in db.session.new if isinstance(p, Pedido) and p.protocolo == "SIC 2026-004790")
    enviado = hoje - timedelta(days=8)
    db.session.add(PedidoConcessionaria(
        pedido=p790, destinatario="Concessionária do Parque Água Branca · canal oficial", enviado_em=enviado,
        prazo=somar_dias_uteis(enviado, 5),
        texto="Em atendimento ao pedido de informação SIC 2026-004790, solicitamos o relatório das vistorias "
              "feitas pela concessionária neste ano e as providências adotadas.\n\nGerência de Parques · Arsesp",
    ))
    registrar_evento(p790, "Pedido padrão enviado à concessionária", p790.responsavel, datetime.combine(enviado, time(15, 0)))

    # 004771: minuta enviada para aprovação ontem, com um item do checklist pendente
    p771 = next(p for p in db.session.new if isinstance(p, Pedido) and p.protocolo == "SIC 2026-004771")
    ontem = datetime.combine(hoje - timedelta(days=1), time(16, 0))
    db.session.add(Minuta(
        pedido=p771, modelo="Em branco", autor=p771.responsavel, enviada_em=ontem, devolucoes=0,
        checklist=["perguntas", "fundamento", "linguagem", "recurso"],
        texto="Prezado(a) cidadão(ã),\n\nEm resposta ao pedido SIC 2026-004771, informamos que os valores do "
              "estacionamento do Parque Cândido Portinari seguem a tabela de preços públicos aprovada pelo poder "
              "concedente, reajustada anualmente conforme o contrato. Encaminhamos em anexo a tabela vigente.\n\n"
              "Caso não concorde com esta resposta, é possível apresentar recurso em até 10 dias pelo Fala.SP."
              "\n\nGerência de Parques · Arsesp",
    ))
    registrar_evento(p771, "Análise concluída: não precisa de informações da concessionária", p771.responsavel, ontem - timedelta(days=2))
    registrar_evento(p771, "Minuta enviada para aprovação (1 item do checklist pendente)", p771.responsavel, ontem)

    for tipo, parque, titulo, resumo, conteudo in DOCUMENTOS:
        db.session.add(Documento(tipo=tipo, parque=parque, titulo=titulo, resumo=resumo, conteudo=conteudo,
                                 cadastrado_por=gerente))
    db.session.commit()
