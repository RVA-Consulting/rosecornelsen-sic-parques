"""Busca simples na base de conhecimento.

Ignora acentos e maiúsculas e exige que todas as palavras apareçam no documento.
A busca é feita em Python porque a base do piloto é pequena; se crescer, dá para
trocar por busca de texto do PostgreSQL sem mudar as telas.
"""

import unicodedata

from .models import Documento


def _normalizar(texto):
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return sem_acento.lower()


def buscar_documentos(termo, parque=None, limite=None):
    palavras = [p for p in _normalizar(termo).split() if len(p) >= 3]
    resultados = []
    for doc in Documento.query.order_by(Documento.cadastrado_em.desc()).all():
        texto = _normalizar(" ".join([doc.tipo, doc.titulo, doc.resumo, doc.conteudo, doc.parque or ""]))
        if all(p in texto for p in palavras):
            resultados.append(doc)
    # Documentos do mesmo parque primeiro, depois os gerais, depois os de outros parques
    if parque:
        resultados.sort(key=lambda d: 0 if d.parque == parque else 1 if not d.parque else 2)
    return resultados[:limite] if limite else resultados
