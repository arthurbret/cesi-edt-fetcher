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
    && pip install --no-cache-dir -r requirements.txt gunicorn

COPY cesi_edt_sync.py cesi_cours_du_jour.py app.py ./

# Force `requests` à utiliser le magasin de certificats système (mis à jour
# ci-dessus) plutôt que son propre bundle certifi embarqué.
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

ENV PORT=8000
EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "--timeout", "60", "app:app"]
