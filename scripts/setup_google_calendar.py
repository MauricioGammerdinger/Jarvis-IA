"""
Configuração inicial do Google Calendar — rode isso UMA VEZ.

Pré-requisito: ter o arquivo `credentials.json` na raiz do projeto (baixado
do Google Cloud Console — veja o passo a passo no README, seção
"Integração com Google Calendar").

Isso abre uma janela do navegador pedindo pra você logar na sua conta Google
e autorizar o JARVIS a acessar seu calendário. Depois de autorizar, salva um
`token.json` na raiz do projeto — esse arquivo é o que o JARVIS usa depois,
sem precisar abrir navegador de novo.

Uso:
    python setup_google_calendar.py
"""

import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main():
    if not CREDENTIALS_PATH.exists():
        print(f"ERRO: não encontrei {CREDENTIALS_PATH}")
        print("Baixe o credentials.json do Google Cloud Console primeiro")
        print("(veja o README, seção 'Integração com Google Calendar').")
        sys.exit(1)

    print("Abrindo o navegador para você autorizar o acesso ao Google Calendar...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)

    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    print(f"\nPronto! Token salvo em {TOKEN_PATH}.")
    print("O JARVIS já pode usar o Google Calendar agora — reinicie-o se estiver rodando.")


if __name__ == "__main__":
    main()
