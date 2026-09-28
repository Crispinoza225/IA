"""L'envoi des e-mails (réinitialisation du mot de passe).

Sans serveur SMTP configuré, le message est affiché dans la console du serveur : pratique pour essayer en local.
"""

import smtplib
import ssl
from email.message import EmailMessage


def envoyer(config, destinataire, sujet, texte):
    if not config.smtp_hote:
        print(f"\n✉️  E-mail pour {destinataire} — {sujet}\n{texte}\n", flush=True)
        return
    message = EmailMessage()
    message["From"] = config.smtp_expediteur
    message["To"] = destinataire
    message["Subject"] = sujet
    message.set_content(texte)
    with smtplib.SMTP(config.smtp_hote, config.smtp_port, timeout=20) as serveur:
        serveur.starttls(context=ssl.create_default_context())
        if config.smtp_utilisateur:
            serveur.login(config.smtp_utilisateur, config.smtp_mot_de_passe)
        serveur.send_message(message)
