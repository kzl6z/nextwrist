"""Formules de sous-titrage produites par Whisper sur le quasi-silence.

Whisper a ete entraine sur des sous-titres : prive de parole claire, il rend
ce qui terminait ces fichiers plutot qu'une chaine vide. Envoyees telles
quelles au modele de langue, ces phrases coutaient 22 secondes de reflexion
sur une demande que personne n'avait formulee.
"""

from nova.voice.transcribe import est_hallucination


def test_reconnait_la_formule_observee():
    # Relevee dans les logs de la machine.
    assert est_hallucination("les sous-titres réalisés par la communauté d'Amara.org")
    assert est_hallucination("Sous-titres réalisés par la communauté d'Amara.org")


def test_reconnait_les_autres_formules_courantes():
    assert est_hallucination("Sous-titrage Société Radio-Canada")
    assert est_hallucination("Merci d'avoir regardé cette vidéo !")
    assert est_hallucination("Abonnez-vous à la chaîne")


def test_laisse_passer_une_vraie_demande():
    assert not est_hallucination("Nova, quelle heure est-il ?")
    assert not est_hallucination("Ouvre le dossier du projet")
    assert not est_hallucination("")


def test_laisse_passer_une_phrase_qui_parle_de_sous_titres():
    # Une vraie demande sur le sujet ne doit pas etre confondue avec la
    # formule : elle est plus longue, et c'est ce qui les distingue.
    assert not est_hallucination(
        "Nova, peux-tu me trouver les sous-titres realises pour la video "
        "que j'ai enregistree hier soir avec la camera du salon ?"
    )
