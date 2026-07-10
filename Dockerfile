FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# sts.viacesi.fr (ADFS, ferme derrière un load-balancer) sert parfois une
# chaîne TLS INCOMPLÈTE : le certificat *.viacesi.fr arrive sans son
# intermédiaire "Gandi RSA Organization Validation Secure Server CA 4".
# Les navigateurs s'en sortent (cache/AIA fetching), mais OpenSSL/requests
# échoue avec "unable to get local issuer certificate" — d'où l'erreur vue
# sur le VPS alors que la même image fonctionne ailleurs. On embarque donc
# l'intermédiaire ET sa racine Sectigo dans le magasin système : OpenSSL peut
# alors reconstruire la chaîne même si le serveur n'envoie que la feuille.
COPY certs/gandi-rsa-ov-secure-server-ca-4.pem /usr/local/share/ca-certificates/gandi-rsa-ov-secure-server-ca-4.crt
COPY certs/sectigo-public-server-auth-root-r46.pem /usr/local/share/ca-certificates/sectigo-public-server-auth-root-r46.crt
RUN update-ca-certificates

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY cesi_edt_sync.py cesi_cours_du_jour.py app.py ./

# Force `requests` à utiliser le magasin de certificats système (mis à jour
# ci-dessus) plutôt que son propre bundle certifi embarqué.
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

ENV PORT=8000
EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "--timeout", "60", "app:app"]
