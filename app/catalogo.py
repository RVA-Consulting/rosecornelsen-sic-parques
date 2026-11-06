"""Listas fixas do sistema (áreas, assuntos, parques, etapas) e regras de prazo da LAI."""

AREAS = [
    "Gerência de Parques",
    "Gerência de Saneamento",
    "Gerência de Gás",
    "Gerência de Energia",
]
AREA_PILOTO = "Gerência de Parques"

ASSUNTOS = [
    "Contrato · obras e cronograma",
    "Contrato · manutenção",
    "Contrato · tarifas",
    "Contrato · outorga",
    "Fiscalização da Arsesp",
    "Fiscalização da Arsesp · penalidades",
    "Pedido de vista de processo",
    "Outro assunto",
]

PARQUES = ["Água Branca", "Villa-Lobos", "Cândido Portinari"]

# código -> (número da etapa no fluxo, rótulo exibido)
ETAPAS = {
    "reclassificar": (2, "Devolvido à Ouvidoria"),
    "validar": (3, "Validar assunto"),
    "fila": (3, "Fila"),
    "analise": (4, "Análise"),
    "concessionaria": (5, "Concessionária"),
    "minuta": (6, "Minuta"),
    "aprovacao": (7, "Aprovação"),
    "envio": (8, "Envio"),
    "concluido": (9, "Concluído"),
}
# Etapas em que o pedido está com um técnico (contam na carga da equipe)
ETAPAS_COM_TECNICO = ["analise", "concessionaria", "minuta", "envio"]

PERFIS = {
    "ouvidoria": "Ouvidoria",
    "gerente": "Gerente de Parques",
    "tecnico": "Técnico(a) de Parques",
}

TIPOS_DOCUMENTO = [
    "Contrato",
    "Normativo Arsesp",
    "Normativo do poder concedente",
    "Resposta anterior",
]

# Destinatário padrão do pedido de informações, por parque
CONCESSIONARIAS = {p: f"Concessionária do Parque {p} · canal oficial" for p in PARQUES}

# Opções de prazo (em dias úteis) para a concessionária responder
PRAZOS_CONCESSIONARIA = [5, 3]
PRAZOS_COBRANCA = [2, 3]

# Modelos de resposta ao cidadão. {protocolo} e {parque} são preenchidos pelo sistema;
# os trechos entre colchetes o técnico precisa trocar antes de enviar.
_FECHO = (
    "\n\nCaso não concorde com esta resposta, é possível apresentar recurso em até 10 dias pelo Fala.SP."
    "\n\nGerência de Parques · Arsesp"
)
MODELOS_RESPOSTA = {
    "Contrato · cronograma e obras": (
        "Prezado(a) cidadão(ã),\n\nEm resposta ao pedido {protocolo}, encaminhamos em anexo o cronograma das obras "
        "obrigatórias do contrato de concessão do Parque {parque}, com a situação atualizada de cada item.\n\n"
        "[Explique o acompanhamento feito pela Arsesp e cite a cláusula ou o normativo.]" + _FECHO
    ),
    "Contrato · manutenção": (
        "Prezado(a) cidadão(ã),\n\nEm resposta ao pedido {protocolo}, informamos que o contrato de concessão do "
        "Parque {parque} prevê [descreva os serviços e a frequência, citando a cláusula].\n\n"
        "[Informe como a Arsesp fiscaliza esses serviços.]" + _FECHO
    ),
    "Pedido de vista": (
        "Prezado(a) cidadão(ã),\n\nEm resposta ao pedido {protocolo}, informamos que a vista do processo "
        "[número do processo] será concedida [por cópia digital em anexo / mediante agendamento], com a retirada "
        "das informações pessoais e sigilosas, conforme a LAI." + _FECHO
    ),
    "Informação inexistente": (
        "Prezado(a) cidadão(ã),\n\nEm resposta ao pedido {protocolo}, informamos que a Arsesp não possui a "
        "informação solicitada, pois [explique o motivo]. [Se souber, indique o órgão que pode ter a informação.]"
        + _FECHO
    ),
    "Em branco": "",
}
# Modelo sugerido conforme o assunto do pedido
MODELO_POR_ASSUNTO = {
    "Contrato · obras e cronograma": "Contrato · cronograma e obras",
    "Contrato · manutenção": "Contrato · manutenção",
    "Pedido de vista de processo": "Pedido de vista",
}

CHECKLIST = {
    "perguntas": "Respondeu a todas as perguntas do pedido",
    "fundamento": "Citou a cláusula ou o normativo que fundamenta a resposta",
    "linguagem": "Linguagem simples, sem siglas sem explicação",
    "dados_pessoais": "Retirou dados pessoais e informações sigilosas dos anexos",
    "recurso": "Informou o prazo de recurso",
}

# LAI: 20 dias corridos a partir do registro, prorrogáveis por mais 10
PRAZO_LAI_DIAS = 20
PRORROGACAO_DIAS = 10
# Pedidos que vencem em até este número de dias aparecem em laranja no painel
ALERTA_DIAS = 5
