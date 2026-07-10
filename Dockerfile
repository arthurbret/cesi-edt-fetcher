FROM python:3.12-slim

WORKDIR /app

# Certificats CA à jour : sans ça, les requêtes HTTPS vers sts.viacesi.fr
# (et d'autres sites) échouent avec "unable to get local issuer certificate"
# sur les images slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade certifi \
    && pip install --no-cache-dir -r requirements.txt gunicorn \
    # sts.viacesi.fr (ADFS) présente un certificat *.viacesi.fr dont la chaîne
    # remonte à la racine "Sectigo Public Server Authentication Root R46".
    # Cette racine est ABSENTE du magasin ca-certificates de Debian slim (selon
    # la version livrée au build) -> échec "unable to get local issuer
    # certificate". Le bundle certifi de Python, lui, la contient. On le fusionne
    # dans le magasin système pour garantir la présence de la racine, quel que
    # soit l'environnement de build.
    && cat "$(python -c 'import certifi; print(certifi.where())')" \
       >> /etc/ssl/certs/ca-certificates.crt

COPY cesi_edt_sync.py cesi_cours_du_jour.py app.py ./

# Force `requests` à utiliser le magasin de certificats système (mis à jour
# ci-dessus) plutôt que son propre bundle certifi embarqué.
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

ENV PORT=8000
EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "--timeout", "60", "app:app"]
