"""Le paiement du Pass Mémoire avec Stripe Checkout (ou un mode démonstration sans paiement réel).

Stripe héberge la page de paiement : les numéros de carte ne passent jamais par Rédigo. Quand le paiement
est confirmé, Stripe prévient le serveur par un « webhook » signé, et le Pass est activé.
"""

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

API_STRIPE = "https://api.stripe.com/v1"
TOLERANCE = 300  # secondes : au-delà, une notification signée est refusée (protection contre le rejeu)


class ErreurPaiement(Exception):
    pass


def creer_session_stripe(cle_secrete, utilisateur, montant, url_base):
    """Crée une page de paiement Stripe et renvoie son adresse."""
    parametres = {
        "mode": "payment",
        "success_url": f"{url_base}/app?paiement=reussi",
        "cancel_url": f"{url_base}/app?paiement=annule",
        "client_reference_id": str(utilisateur["id"]),
        "customer_email": utilisateur["email"],
        "metadata[utilisateur_id]": str(utilisateur["id"]),
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "eur",
        "line_items[0][price_data][unit_amount]": str(montant),
        "line_items[0][price_data][product_data][name]": "Rédigo — Pass Mémoire (12 mois)",
    }
    requete = urllib.request.Request(f"{API_STRIPE}/checkout/sessions",
                                     data=urllib.parse.urlencode(parametres).encode(),
                                     headers={"Authorization": f"Bearer {cle_secrete}"})
    try:
        with urllib.request.urlopen(requete, timeout=20) as reponse:
            return json.loads(reponse.read())["url"]
    except urllib.error.HTTPError as erreur:
        try:
            message = json.loads(erreur.read())["error"]["message"]
        except (ValueError, KeyError):
            message = f"erreur {erreur.code}"
        raise ErreurPaiement(f"Stripe a refusé la demande : {message}")
    except (urllib.error.URLError, OSError, KeyError, ValueError) as erreur:
        raise ErreurPaiement(f"Impossible de joindre Stripe : {erreur}")


def signer(corps, secret, horodatage):
    """La signature que Stripe place dans l'en-tête Stripe-Signature (utile aussi pour les tests)."""
    message = f"{horodatage}.".encode() + corps
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verifier_signature(corps, entete, secret, maintenant=None):
    """Vérifie qu'une notification vient bien de Stripe et qu'elle est récente."""
    maintenant = time.time() if maintenant is None else maintenant
    horodatage, signatures = None, []
    for partie in (entete or "").split(","):
        cle, _, valeur = partie.strip().partition("=")
        if cle == "t":
            horodatage = valeur
        elif cle == "v1":
            signatures.append(valeur)
    if not horodatage or not signatures or not horodatage.isdigit():
        return False
    if abs(maintenant - int(horodatage)) > TOLERANCE:
        return False
    attendue = signer(corps, secret, horodatage)
    return any(hmac.compare_digest(attendue, s) for s in signatures)


def traiter_evenement(base, evenement):
    """Active le Pass quand un paiement est confirmé. Renvoie True si un Pass a été activé."""
    if evenement.get("type") not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return False
    session = evenement.get("data", {}).get("object", {})
    if session.get("payment_status") != "paid":
        return False
    try:
        utilisateur_id = int(session.get("client_reference_id") or session.get("metadata", {}).get("utilisateur_id"))
    except (TypeError, ValueError):
        return False
    return base.activer_pass(utilisateur_id, "stripe", session.get("id", ""), int(session.get("amount_total") or 0))
