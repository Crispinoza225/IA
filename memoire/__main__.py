"""Point d'entrée.

  python3 -m memoire                                   lance la plateforme dans le navigateur
  python3 -m memoire convertir texte.md --docx m.docx  met en forme sans interface
"""

import argparse
import json


def main():
    parser = argparse.ArgumentParser(prog="python3 -m memoire", description="Mise en forme automatique de mémoire.")
    actions = parser.add_subparsers(dest="action")
    p = actions.add_parser("lancer", help="lance la plateforme web (action par défaut)")
    p.add_argument("--port", type=int, default=8050)
    p.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir le navigateur automatiquement")
    p = actions.add_parser("convertir", help="met en forme un fichier texte, sans interface")
    p.add_argument("source", help="le texte du mémoire (syntaxe # Titre, **gras**…)")
    p.add_argument("--docx", help="fichier Word à créer")
    p.add_argument("--pdf", help="fichier PDF à créer")
    p.add_argument("--projet", help="réglages : un projet .json enregistré depuis la plateforme")
    args = parser.parse_args()

    if args.action == "convertir":
        from .reglages import Reglages
        from .source import lire, numeroter
        reglages = Reglages()
        if args.projet:
            with open(args.projet, encoding="utf-8") as f:
                reglages = Reglages.depuis_dict(json.load(f).get("reglages"))
        with open(args.source, encoding="utf-8") as f:
            blocs = numeroter(lire(f.read()), reglages.numerotation)
        if args.docx:
            from .docx import ecrire_docx
            with open(args.docx, "wb") as f:
                f.write(ecrire_docx(blocs, reglages))
            print(f"✅ {args.docx}")
        if args.pdf:
            from .pdf import ecrire_pdf
            with open(args.pdf, "wb") as f:
                f.write(ecrire_pdf(blocs, reglages)[0])
            print(f"✅ {args.pdf}")
        if not args.docx and not args.pdf:
            parser.error("indique --docx et/ou --pdf")
    else:
        from .serveur import servir
        servir(getattr(args, "port", 8050), not getattr(args, "sans_navigateur", False))


if __name__ == "__main__":
    main()
