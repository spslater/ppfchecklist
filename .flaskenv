FLASK_APP=ppfchecklist
FLASK_RUN_PORT=80
FLASK_RUN_HOST=0.0.0.0
FLASK_ENV=development
FLASK_DEBUG=True

PPF_BASEDIR="."
PPF_DATABASE="sqlite.db"
PPF_LOGFILE="output.log"
PPF_LOGLEVEL="DEBUG"
PPF_AUTHORIZE=false

SECRET_KEY="SomethingNotEntirelySecret"
OIDC_CLIENT_SECRETS="client_secrets.json.sample"
OIDC_VALID_ISSUERS="http://localhost:8080/auth/realms/ppfchecklist"
OIDC_OPENID_REALM="http://localhost/oidc_callback"