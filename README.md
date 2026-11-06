# SIC Parques

Sistema para acompanhar os pedidos de informação ao cidadão (SIC/LAI) que chegam pelo Fala.SP
e são tratados pela Ouvidoria e pela Gerência de Parques da Arsesp.

- Protótipo das telas: https://claude.ai/artifact/6A5zr8tAm9row4r4mUKQp4
- Fluxo TO-BE: `../fluxo-sic-parques-tobe.bpmn`

## Situação

| Etapa | Tela | Situação |
|---|---|---|
| 1 | Painel de prazos | pronta |
| 2 | Registro na Ouvidoria (e reclassificação de pedidos devolvidos) | pronta |
| 3 | Fila da Gerência (validar assunto e distribuir) | pronta |
| 4 | Análise do técnico (busca na base de conhecimento, decisão sobre a concessionária) | pronta |
| 5 | Pedido à concessionária (pedido padrão, prazo em dias úteis, cobrança, resposta) | pronta |
| — | Base de conhecimento (consultar e incluir documentos) | pronta |
| 6 | Minuta da resposta (modelos, checklist, alçada do técnico) | pronta |
| 7 | Aprovação do gerente (aprovar ou devolver com motivo) | pronta |
| 8 | Envio e baixa do prazo (copiar, confirmar registro no Fala.SP, guardar na base) | pronta |

Fora do escopo do piloto: integração automática com o Fala.SP e sugestão de texto por IA.

## Regras

- Prazo LAI: 20 dias corridos a partir do registro no Fala.SP, prorrogáveis por mais 10.
- Painel: laranja quando faltam até 5 dias; vermelho quando venceu.
- Assunto duvidoso (novo ou sensível) vai para o gerente validar; ele pode devolver à Ouvidoria.
- Prorrogação da LAI: uma única vez, antes do vencimento, com justificativa (que também deve ir ao cidadão pelo Fala.SP).
- Concessionária: prazo de 5 ou 3 dias úteis (feriados ainda não contam); se vencer, o pedido fica em vermelho e pode ser cobrado com novo prazo.
- O sistema não envia e-mails: o técnico copia o texto e envia pelo canal oficial; anexos ficam lá.
- Só o técnico responsável e o gerente atuam num pedido; a Ouvidoria só consulta.
- Resposta-padrão (modelo validado + checklist completo) segue direto para envio; nova ou sensível vai ao gerente.
- O texto não sai com trechos entre colchetes do modelo sem trocar.
- Ao encerrar, a resposta pode virar "Resposta anterior" na base de conhecimento.
- Cada ação fica no histórico do pedido, com data e responsável.

## Rodar no computador

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # e preencha SECRET_KEY e SEED_SENHA
.venv/bin/flask --app wsgi seed   # cria o banco local com dados de teste (apaga o que existir)
.venv/bin/python wsgi.py          # abre em http://localhost:8000
```

Usuários de teste (senha = `SEED_SENHA` do `.env`): `ouvidoria@teste.local`, `gerente@teste.local`,
`ana@teste.local`, `bruno@teste.local`, `carla@teste.local`.

## Publicar no Render

- Runtime **Python 3**; build `pip install -r requirements.txt`; start `gunicorn wsgi:app --bind 0.0.0.0:$PORT`.
- Variáveis de ambiente: `DATABASE_URL` (Neon), `SECRET_KEY` e, para criar os dados de teste, `SEED_SENHA`.
