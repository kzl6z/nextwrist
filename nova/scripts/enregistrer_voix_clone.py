"""Enregistrer la voix qui servira a fabriquer celle de Nova.

    uv run python scripts/enregistrer_voix_clone.py

POURQUOI CE SCRIPT EXISTE

La voix d'ElevenLabs s'est tue sur un quota epuise, et les voix locales
generalistes (Kokoro, Piper) ne satisfont pas. La seule sortie est un modele
AFFINE sur une voix precise : il ne connait qu'elle, donc il pese 60 Mo la ou
Kokoro en pese 350 avec torch derriere — dix fois plus leger, dix fois plus
rapide, et il ressemble a quelqu'un.

Affiner demande de la matiere : entre 20 et 30 minutes d'audio propre, chaque
extrait accompagne de sa transcription EXACTE. Ce script produit exactement
ca, au format LJSpeech que tous les entraineurs Piper savent lire.

⚠️ CE QUI FAIT LA QUALITE D'UN CLONE, ET CE QUI N'Y CHANGE RIEN

Ce qui compte : la CONSTANCE. Meme piece, meme distance au micro, meme
energie, meme humeur. Un corpus enregistre moitie le matin et moitie le soir
apprend au modele deux voix, et il rend leur moyenne — qui ne ressemble a
personne.

Ce qui ne compte pas : le materiel haut de gamme. Le micro integre de l'iMac
suffit largement, a condition d'etre a 20-30 cm et toujours a la meme place.

C'est pour ca que ce script est REPRENABLE : personne ne lit cent cinquante
phrases d'affilee sans que sa voix ne change de fatigue. Mieux vaut trois
seances de dix minutes, a la meme heure, que trente minutes d'un coup.
"""

from __future__ import annotations

import csv
import sys
import wave
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "data" / "voix-clone"

#: ⚠️ 22 050 Hz, ET PAS LES 16 000 DU BANC WHISPER.
#:
#: C'est le taux natif des modeles Piper « medium ». Enregistrer en 16 kHz
#: puis reechantillonner vers le haut ne rend pas les aigus : ils n'ont jamais
#: ete captes. Le modele affine sonnerait sourd, et rien dans les fichiers ne
#: dirait pourquoi — ils seraient tous parfaitement valides.
TAUX = 22050

#: En dessous : un bruit, un raclement, une phrase avalee.
MIN_SECONDES = 1.0
#: Au-dessus : le micro est reste ouvert, ou la phrase a ete relue deux fois.
MAX_SECONDES = 20.0

#: Niveau sonore acceptable (RMS sur [-1, 1]).
#:
#: Trop bas, le modele apprend le souffle en meme temps que la voix. Trop
#: haut, la saturation ecrete les consonnes et l'affinage apprend l'ecretage.
#: Verifier a l'enregistrement coute une soustraction ; s'en apercevoir apres
#: l'entrainement coute la seance entiere.
RMS_MIN = 0.015
RMS_MAX = 0.30

# ══════════════════════════════════════════════════════════════════════════
#  LE CORPUS
#
#  Quatre familles, et chacune repare un defaut precis d'un clone entraine
#  sur du texte pris au hasard :
#
#    PHONETIQUE   couvre les sons du francais — nasales, liaisons, groupes
#                 consonantiques. Un phoneme absent du corpus est un phoneme
#                 que le modele inventera.
#    NOVA         ce qu'elle dit vraiment. Un modele entraine sur de la prose
#                 litteraire prononce mal « il est 14 h 30 ».
#    QUESTIONS    la prosodie montante. Sans elle, toutes les questions
#                 tombent a plat — c'est le defaut le plus audible des
#                 clones faits a la va-vite.
#    LONGUES      la respiration et le rythme. Des phrases courtes seules
#                 donnent un debit hache.
# ══════════════════════════════════════════════════════════════════════════

PHONETIQUE = (
    "Le vent du nord souffle sur la plaine glacée.",
    "Un grand champ de blé ondule sous le soleil.",
    "Cinq chiens bruns dorment devant la vieille grange.",
    "Ma tante habite un joli pavillon en pierre blanche.",
    "Il pleut des cordes depuis lundi matin sans interruption.",
    "Ces oiseaux migrateurs traversent la Méditerranée chaque automne.",
    "La montagne enneigée brillait d'un éclat presque aveuglant.",
    "Nous partirons demain à l'aube, avant que le brouillard ne tombe.",
    "Son enfance s'est passée entre Toulouse et Perpignan.",
    "Un bruit sourd résonna longuement dans le couloir désert.",
    "Le pain frais embaume toute la cuisine dès le petit matin.",
    "Quinze bateaux blancs mouillaient dans la baie tranquille.",
    "Cette peinture ancienne vaut une véritable fortune.",
    "Le train pour Bordeaux part du quai numéro huit.",
    "J'ai rangé les vieux journaux dans le grenier poussiéreux.",
    "Elle chantonnait un air joyeux en épluchant les légumes.",
    "Le chirurgien expliqua calmement les risques de l'opération.",
    "Une pluie fine tombait sur les toits d'ardoise du village.",
    "Ils ont construit ce pont en moins de trois ans.",
    "Le brouillard enveloppait la forêt d'un silence épais.",
    "Mon oncle collectionne les timbres depuis quarante ans.",
    "Ce roman policier m'a tenu éveillé jusqu'à deux heures du matin.",
    "Les enfants couraient pieds nus sur le sable chaud.",
    "Une odeur de café flottait dans l'appartement.",
    "Le vieux marin racontait ses voyages avec une précision étonnante.",
    "Nous avons longuement discuté de politique et de philosophie.",
    "Cette théorie soulève plus de questions qu'elle n'en résout.",
    "Le ciel s'assombrit brusquement avant l'orage.",
    "Il a échoué trois fois avant de réussir son examen.",
    "La bibliothèque municipale ferme à dix-neuf heures.",
    "Un écureuil roux grimpa le long du tronc noueux.",
    "Elle a hérité d'une maison en ruine dans le Cantal.",
    "Le boulanger pétrit sa pâte chaque nuit à quatre heures.",
    "Ces champignons sont vénéneux, ne les touche surtout pas.",
    "L'orchestre entier se leva sous les applaudissements.",
    "Je n'ai jamais compris pourquoi il est parti si vite.",
    "Un long silence suivit cette déclaration inattendue.",
    "La rivière débordait après huit jours de pluie continue.",
    "Son écriture penchée remplissait des cahiers entiers.",
    "Le vieux chêne a été foudroyé pendant la tempête.",
)

NOVA = (
    "Il est vingt heures. La nuit va bientôt tomber.",
    "Il est huit heures quinze. Ta première réunion commence dans une heure.",
    "Nous sommes le mardi dix-huit août deux mille vingt-six.",
    "Entendu. J'ouvre le dossier du projet.",
    "Je ne trouve pas cette information dans mes notes.",
    "Discord est maintenant fermé.",
    "Le son est réglé à trente pour cent.",
    "Je n'ai pas pu ouvrir cette application. Elle ne semble pas installée.",
    "D'après tes documents, la réunion a été déplacée à jeudi.",
    "Je ne sais pas. Il faudrait vérifier dans tes archives.",
    "Un trou noir est une région où la gravité est si forte que rien ne s'en échappe.",
    "La Terre mesure environ douze mille sept cent quarante kilomètres de diamètre.",
    "Cette idée me paraît fragile sur un point précis.",
    "Tu m'avais dit le contraire la semaine dernière.",
    "Je te le rappelle demain matin à neuf heures.",
    "Trois choses me semblent importantes ici.",
    "C'est noté. Je m'en souviendrai.",
    "La batterie est à vingt-trois pour cent.",
    "Il fait douze degrés dehors, et le ciel est couvert.",
    "Ton prochain rendez-vous est chez le kinésithérapeute.",
    "Je préfère te dire que je ne sais pas plutôt que d'inventer.",
    "Cette source date de deux mille dix-neuf. Elle est peut-être dépassée.",
    "J'ai trouvé quatre documents qui parlent de ce sujet.",
    "Le fichier a bien été enregistré sur ton bureau.",
    "Photos est ouvert. Que cherches-tu exactement ?",
)

QUESTIONS = (
    "Est-ce que tu veux que je continue ?",
    "Veux-tu que je t'en dise plus sur ce point ?",
    "Qu'est-ce qu'un trou noir, exactement ?",
    "Quelle heure est-il ?",
    "Quel jour sommes-nous aujourd'hui ?",
    "Tu es sûr de vouloir fermer cette application ?",
    "Dois-je noter ça dans tes souvenirs ?",
    "Combien de temps veux-tu que ça dure ?",
    "Pourquoi le ciel est-il bleu ?",
    "As-tu vraiment besoin de tout ce détail ?",
    "Qui t'a raconté cette histoire ?",
    "Où as-tu rangé le dossier dont tu me parlais ?",
    "Est-ce bien ce que tu voulais dire ?",
    "Combien coûte cet abonnement par mois ?",
    "Faut-il que je te réveille plus tôt demain ?",
)

LONGUES = (
    "Quand je repense à cette période, je me dis que nous aurions pu agir "
    "beaucoup plus tôt, mais personne n'avait vu venir ce qui allait arriver.",
    "La difficulté n'est pas de trouver une réponse, c'est de savoir laquelle "
    "des trois questions posées mérite vraiment qu'on s'y attarde.",
    "Il faut d'abord vérifier que le service est lancé, ensuite que la clé est "
    "valide, et seulement après se demander si le modèle est en cause.",
    "Ce qui m'a frappé dans son récit, ce n'est pas tant les faits eux-mêmes "
    "que la façon tranquille dont il les racontait, comme s'il parlait "
    "de quelqu'un d'autre.",
    "Nous avons passé la matinée à chercher une panne de réseau alors que le "
    "problème venait simplement d'un câble mal enfoncé derrière le meuble.",
    "Si tu veux que je retienne quelque chose durablement, dis-le moi "
    "explicitement, sinon je considère que c'est une information de passage.",
    "Le plus difficile dans ce métier n'est pas d'apprendre les techniques, "
    "c'est de savoir laquelle appliquer devant un cas qu'on n'a jamais vu.",
    "En relisant mes notes de l'an dernier, je me rends compte que j'avais "
    "déjà identifié ce risque, sans jamais prendre le temps de le traiter.",
    "L'électricien est passé ce matin, il a changé le tableau complet et "
    "vérifié toutes les prises de la maison, ça nous a pris trois heures.",
    "Je peux te répondre tout de suite, mais je préfère te prévenir que ma "
    "réponse repose sur des documents qui datent de plus de deux ans.",
)

#: ⚠️ LE CORPUS DOIT FAIRE 20 A 30 MINUTES DITES, PAS « UN BON ECHANTILLON ».
#:
#: La premiere version en comptait quatre-vingt-dix — six minutes. C'est la
#: quantite qui aurait paru raisonnable a la lecture, et qui aurait produit un
#: modele metallique dont personne n'aurait su dire pourquoi : un affinage
#: sous-alimente ne rate pas bruyamment, il rend une voix approximative.
#:
#: A cent cinquante mots par minute, vingt-cinq minutes valent trois mille
#: sept cents mots. C'est ce chiffre-la qui commande la taille du corpus, pas
#: le nombre de phrases.
RECITS = (
    "Le lendemain matin, il s'est levé bien avant le reste de la maison pour "
    "profiter du calme et finir la lettre qu'il repoussait depuis des semaines.",
    "Nous marchions depuis deux heures quand le sentier s'est brusquement "
    "interrompu devant un éboulement que personne n'avait signalé.",
    "Elle a posé sa tasse, regardé longuement par la fenêtre, puis annoncé "
    "qu'elle partait vivre à l'étranger l'année suivante.",
    "Ce village n'a pratiquement pas changé depuis mon enfance, sauf que la "
    "boulangerie a fermé et que l'école ne compte plus qu'une seule classe.",
    "Mon grand-père réparait lui-même tout ce qui tombait en panne, et il "
    "gardait dans son atelier des pièces dont il ne savait plus l'origine.",
    "Après le dîner, la conversation a dérivé vers des sujets plus graves, et "
    "personne n'a osé la ramener vers quelque chose de léger.",
    "Le concert devait commencer à vingt heures, mais un problème technique "
    "a repoussé le début de près de quarante minutes.",
    "Il avait promis de rappeler avant la fin de la semaine, et nous sommes "
    "restés sans nouvelles pendant presque un mois entier.",
    "La maison sentait la cire et le bois humide, exactement comme dans mon "
    "souvenir, et j'ai retrouvé chaque grincement du parquet.",
    "En descendant vers la plage, on aperçoit d'abord les toits rouges, puis "
    "la digue, et enfin cette longue bande de sable presque déserte.",
    "Ils se sont rencontrés à la fac, se sont perdus de vue pendant dix ans, "
    "puis retrouvés par hasard dans un train pour Marseille.",
    "La réunion s'est éternisée parce que chacun voulait rappeler ce qu'il "
    "avait déjà dit lors de la réunion précédente.",
    "Le chat s'est installé sur le rebord de la fenêtre et n'a plus bougé de "
    "tout l'après-midi, sauf pour suivre le soleil.",
    "Nous avons repeint la chambre en trois jours, en commençant par le "
    "plafond, ce qui était une erreur que nous avons vite comprise.",
    "Cette photographie date de mille neuf cent soixante-douze, et pourtant "
    "les visages qu'on y voit semblent étrangement contemporains.",
    "Il m'a expliqué le fonctionnement de la machine avec une patience que je "
    "n'aurais jamais eue à sa place.",
    "Le vieux libraire connaissait chacun de ses clients par son prénom et se "
    "souvenait de ce qu'ils avaient acheté trois ans plus tôt.",
    "Quand l'orage a éclaté, nous étions encore à découvert, et il a fallu "
    "courir près d'un kilomètre pour trouver un abri.",
    "Elle a appris le piano sur le tard, à quarante-cinq ans, et joue "
    "aujourd'hui mieux que beaucoup de gens qui ont commencé enfants.",
    "Le déménagement a duré deux jours pleins, et nous avons découvert des "
    "cartons jamais ouverts depuis le précédent déménagement.",
    "Il régnait dans cette salle d'attente un silence gêné que personne ne "
    "cherchait vraiment à rompre.",
    "La route serpente entre les vignes pendant une vingtaine de kilomètres "
    "avant de rejoindre la nationale.",
    "J'ai relu ce passage trois fois sans parvenir à décider s'il fallait le "
    "prendre au sérieux ou comme une plaisanterie.",
    "Le facteur passe désormais tous les deux jours, ce qui a modifié toutes "
    "les habitudes du quartier sans que personne ne s'en plaigne.",
    "Sa voix tremblait légèrement au début du discours, puis elle a trouvé "
    "son rythme et n'a plus regardé ses notes.",
    "Nous avons planté ce cerisier l'année de sa naissance, et il donne "
    "maintenant plus de fruits que nous ne pouvons en manger.",
    "Le magasin ferme définitivement à la fin du mois, après cinquante-trois "
    "ans d'ouverture quotidienne.",
    "Il faisait si froid ce matin-là que la serrure avait gelé et qu'il a "
    "fallu attendre midi pour entrer.",
    "Cette histoire circule depuis si longtemps que plus personne ne sait "
    "quelle part en est vraie.",
    "Le train a été retardé, puis annulé, et nous avons finalement pris un "
    "car qui mettait deux fois plus de temps.",
)

QUOTIDIEN = (
    "Je passe à la pharmacie en rentrant, tu as besoin de quelque chose ?",
    "Le rendez-vous est confirmé pour jeudi quatorze heures trente.",
    "N'oublie pas de sortir les poubelles, c'est le ramassage demain matin.",
    "Il reste du poulet et des haricots verts dans le réfrigérateur.",
    "La machine à laver fait un bruit bizarre depuis hier soir.",
    "J'ai réservé une table pour quatre personnes à vingt heures.",
    "Le colis devrait arriver entre mardi et vendredi prochain.",
    "Tu peux baisser un peu le chauffage, il fait vraiment trop chaud ici.",
    "On se retrouve devant la gare, côté sortie sud, vers dix-sept heures.",
    "J'ai oublié mes clés à l'intérieur, heureusement que la fenêtre était ouverte.",
    "Le médecin m'a prescrit trois séances par semaine pendant un mois.",
    "Les enfants rentrent de l'école à seize heures quarante-cinq.",
    "Il faut renouveler l'abonnement avant la fin du mois, sinon il se coupe.",
    "J'ai payé cent quatre-vingt-douze euros pour la réparation complète.",
    "Le rendez-vous chez le dentiste tombe en même temps que la réunion.",
    "On a marché presque huit kilomètres, je sens mes jambes ce soir.",
    "Je ne retrouve plus le document que tu m'as envoyé la semaine dernière.",
    "La réunion de lundi est décalée à mercredi, même heure, même salle.",
    "Il faudrait racheter du café, il n'en reste presque plus.",
    "J'arrive dans dix minutes, je suis coincé dans les embouteillages.",
    "Le vol décolle à six heures vingt, donc il faut partir à quatre heures.",
    "Ça fait trois fois que j'essaie de les joindre sans aucune réponse.",
    "Tu préfères qu'on y aille en voiture ou qu'on prenne le train ?",
    "J'ai laissé le double des clés chez la voisine du troisième étage.",
    "Le devis s'élève à deux mille quatre cents euros, pose comprise.",
)

TECHNIQUE = (
    "Le fichier pèse quatre-vingt-douze mégaoctets, ce qui est trop lourd pour un courriel.",
    "Vérifie d'abord que le service tourne, ensuite seulement que la clé est valide.",
    "La mémoire vive est saturée, c'est pour ça que tout ralentit d'un coup.",
    "Le modèle met environ quatre secondes avant de prononcer son premier mot.",
    "Il faut redémarrer l'application pour que la nouvelle valeur soit prise en compte.",
    "La sauvegarde s'est faite automatiquement à trois heures du matin.",
    "Ce réglage n'a aucun effet tant que le service n'a pas été relancé.",
    "Le disque est plein à quatre-vingt-quinze pour cent, il faudrait faire du tri.",
    "L'erreur venait d'un simple espace en trop à la fin de la ligne.",
    "La connexion a été interrompue au bout de trente secondes d'attente.",
    "Ce format demande un abonnement payant, contrairement à ce qui est écrit.",
    "Le mot de passe expire tous les quatre-vingt-dix jours, sans prévenir.",
    "J'ai comparé les deux versions et la différence tient en une seule ligne.",
    "Le processeur monte à quatre-vingts pour cent dès que la synthèse démarre.",
    "Une mise à jour est disponible, elle corrige onze failles de sécurité.",
    "Le quota mensuel est de dix mille crédits, et il en reste trois.",
    "Cette opération est irréversible, il n'y aura pas de confirmation ensuite.",
    "Le résultat est correct, mais il a mis quarante secondes à s'afficher.",
    "Il vaut mieux mesurer que deviner, surtout quand tout semble normal.",
    "Un message d'erreur doit dire quoi faire, pas seulement ce qui a échoué.",
)

NUANCES = (
    "Non, franchement, je ne suis pas d'accord avec cette conclusion.",
    "Attends, laisse-moi réfléchir une seconde avant de répondre.",
    "C'est exactement ça ! Tu as mis le doigt sur le vrai problème.",
    "Hmm… je ne suis pas certain que ce soit la bonne approche.",
    "Bien sûr, aucun souci, je m'en occupe tout de suite.",
    "Ah non, ça par contre, c'est une très mauvaise idée.",
    "Doucement, tu vas beaucoup trop vite pour moi.",
    "Voilà. C'est fait. Tu peux vérifier quand tu veux.",
    "Je comprends ton point de vue, mais il manque un élément important.",
    "Écoute, on en reparlera demain, il est vraiment tard.",
    "Tant mieux ! Je craignais que ce soit plus compliqué.",
    "Ça m'étonnerait beaucoup, mais je peux me tromper.",
    "Alors là, je n'en ai absolument aucune idée.",
    "Parfait. On fait comme ça et on n'en parle plus.",
    "Tu es sûr ? Parce que ça change tout, si c'est le cas.",
    "Oui, enfin… en théorie. En pratique, c'est un peu différent.",
    "Je préfère être clair : ça ne marchera pas comme tu l'imagines.",
    "D'accord, mais alors il faut tout reprendre depuis le début.",
    "Excellente question. Et la réponse est moins simple qu'elle en a l'air.",
    "Voilà exactement le genre de détail qu'on oublie toujours.",
)

#: ⚠️ « œ » ETAIT ABSENT DES DEUX PREMIERES VERSIONS DU CORPUS.
#:
#: Verifie par comptage, pas a la relecture : zero occurrence sur cent
#: quatre-vingt-cinq phrases. Or « cœur », « sœur », « œuvre », « bœuf »,
#: « vœu », « œil » sont des mots du quotidien. Un phoneme absent du corpus
#: n'est pas un phoneme que le modele prononce mal : c'est un phoneme qu'il
#: INVENTE, en interpolant depuis ce qu'il connait — et le resultat s'entend
#: precisement sur les mots qu'on emploie le plus.
#:
#: Le meme comptage a servi a verifier « gn », « ill » et « tion ». Une
#: couverture phonetique se mesure ; elle ne se juge pas a l'oeil.
COMPLEMENT = (
    "Il a le cœur solide, mais le moral en berne depuis quelques semaines.",
    "Ma sœur aînée travaille comme chef d'œuvre restauratrice au musée du Louvre.",
    "Le bœuf bourguignon mijote depuis quatre heures et embaume toute la maison.",
    "J'ai fait le vœu de ne plus jamais recommencer cette erreur.",
    "Il n'a pas fermé l'œil de la nuit à cause du bruit des travaux.",
    "Cette œuvre de jeunesse annonce déjà tout ce qu'il écrira plus tard.",
    "Le nœud était si serré qu'il a fallu couper la corde.",
    "Un œuf frais se reconnaît à la fermeté de son blanc.",
    "Ils travaillent de concert, œuvrant chacun de son côté sur la même idée.",
    "Le chœur de l'église résonnait encore longtemps après le dernier chant.",
    "Elle a rangé ses affaires avec un soin méticuleux avant de refermer la valise.",
    "Le peintre travaillait uniquement à la lumière naturelle, jamais après le crépuscule.",
    "Nous avons hésité longtemps entre les deux propositions avant de trancher.",
    "Le vieux moulin fonctionne encore, une fois par an, pour la fête du village.",
    "Il pleuvait tellement que les gouttières débordaient de tous les côtés.",
    "La cheminée tirait mal, et la pièce s'est remplie de fumée en quelques minutes.",
    "Son témoignage a complètement changé la direction de l'enquête.",
    "Le jardin descend en pente douce jusqu'à un petit ruisseau bordé de saules.",
    "Ce fromage vient d'une ferme située à quelques kilomètres seulement.",
    "L'ascenseur est en panne depuis trois jours, et nous habitons au sixième.",
    "Ils ont finalement choisi de vendre la maison plutôt que de la restaurer.",
    "Le brouillard était si dense qu'on ne voyait pas le capot de la voiture.",
    "Cette recette demande une cuisson lente et une surveillance constante.",
    "Le stationnement est payant du lundi au samedi, de neuf heures à dix-neuf heures.",
    "J'ai croisé ton frère hier au marché, il m'a semblé en pleine forme.",
    "Les travaux devraient s'achever avant la fin du printemps prochain.",
    "Elle explique toujours deux fois, la seconde plus lentement que la première.",
    "Ce chemin longe la falaise et offre une vue exceptionnelle sur toute la baie.",
    "Le clocher penche légèrement vers l'ouest depuis le tremblement de terre.",
    "Nous avons acheté ces meubles d'occasion, et ils tiendront encore vingt ans.",
    "Le silence qui a suivi valait toutes les réponses possibles.",
    "Il gagne correctement sa vie, mais au prix d'une fatigue considérable.",
    "La bibliothèque contient plus de huit mille volumes, tous classés à la main.",
    "Ce vin gagne à vieillir quelques années encore avant d'être ouvert.",
    "Les hirondelles reviennent chaque année exactement au même endroit.",
    "L'inauguration aura lieu le premier samedi de septembre, en fin de matinée.",
    "Il a suffi d'une phrase maladroite pour gâcher toute la soirée.",
    "Cette montre appartenait à mon arrière-grand-père et fonctionne toujours.",
    "Le pont a été fermé à la circulation pour cause de travaux urgents.",
    "Je n'aurais jamais imaginé qu'un détail pareil puisse tout faire basculer.",
    "Les nuages s'écartent enfin, et le soleil éclaire la vallée entière.",
    "Il range ses outils dans le même ordre depuis quarante ans.",
    "Le voisin tond sa pelouse tous les dimanches matin, sans exception.",
    "Cette porte grince affreusement, il faudrait huiler les gonds.",
    "Nous avons dormi dans une auberge minuscule tenue par un couple charmant.",
    "Le professeur nous demandait de justifier chaque étape du raisonnement.",
    "Le vent a arraché plusieurs tuiles pendant la nuit de dimanche à lundi.",
    "Elle prépare son concours depuis dix-huit mois avec une régularité impressionnante.",
    "Le train traversait des paysages que je n'avais encore jamais vus.",
    "Il vaut mieux poser la question maintenant que de le regretter ensuite.",
    "Cette décision engage l'ensemble de l'équipe pour les trois années à venir.",
    "Le chemin était boueux, glissant, et nous n'avions pas les bonnes chaussures.",
    "Un rayon de soleil traversait le vitrail et projetait des taches colorées.",
    "Il s'est excusé longuement, mais le mal était déjà fait.",
    "La récolte de cette année dépasse toutes les prévisions des agriculteurs.",
    "Le manuscrit original a été retrouvé dans les archives d'une abbaye.",
    "Nous sommes restés silencieux pendant tout le trajet du retour.",
    "Cette méthode fonctionne parfaitement, à condition de la suivre entièrement.",
    "Le chien a aboyé toute la nuit, et personne n'a compris pourquoi.",
    "Il faudrait vraiment que quelqu'un vérifie ces chiffres avant la publication.",
)

CORPUS: tuple[str, ...] = (
    PHONETIQUE + NOVA + QUESTIONS + LONGUES + RECITS
    + QUOTIDIEN + TECHNIQUE + NUANCES + COMPLEMENT
)


def _rms(pcm: bytes) -> float:
    """Niveau moyen du signal, sur [-1, 1]. Sans numpy : `array` suffit."""
    from array import array

    if not pcm:
        return 0.0
    echantillons = array("h")
    echantillons.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if sys.byteorder == "big":
        echantillons.byteswap()
    if not echantillons:
        return 0.0
    somme = sum((v / 32768.0) ** 2 for v in echantillons)
    return (somme / len(echantillons)) ** 0.5


def _ecrire_wav(chemin: Path, pcm: bytes) -> None:
    with wave.open(str(chemin), "wb") as fichier:
        fichier.setnchannels(1)
        fichier.setsampwidth(2)
        fichier.setframerate(TAUX)
        fichier.writeframes(pcm)


def _deja_faites(dossier: Path) -> dict[int, str]:
    """Ce qui est deja enregistre, lu depuis `metadata.csv`.

    ⚠️ LA REPRISE SE LIT SUR LE DISQUE, PAS DANS UN COMPTEUR.

    Un compteur separe se desynchronise du premier fichier supprime a la main
    — et on refait alors une phrase deja faite tout en en sautant une autre,
    sans que rien ne le signale. La verite est dans les fichiers.
    """
    fiche = dossier / "metadata.csv"
    if not fiche.exists():
        return {}
    faites: dict[int, str] = {}
    with fiche.open(encoding="utf-8", newline="") as f:
        for ligne in csv.reader(f, delimiter="|"):
            if len(ligne) >= 2 and ligne[0].startswith("phrase-"):
                try:
                    faites[int(ligne[0].split("-")[1])] = ligne[1]
                except (IndexError, ValueError):
                    continue
    return faites


def _ajouter_a_la_fiche(dossier: Path, identifiant: str, texte: str) -> None:
    """Format LJSpeech : `id|texte|texte`, separe par des barres verticales.

    Le texte est ecrit DEUX FOIS a dessein : la premiere colonne est la
    transcription brute, la seconde la version « normalisee » (chiffres
    ecrits en toutes lettres, abreviations developpees). Ici les deux sont
    identiques parce que le corpus est deja ecrit tel qu'il se prononce —
    c'est pour ca qu'il dit « vingt heures » et jamais « 20 h ».
    """
    with (dossier / "metadata.csv").open("a", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter="|", quoting=csv.QUOTE_NONE, escapechar="\\").writerow(
            [identifiant, texte, texte]
        )


def _duree(pcm: bytes) -> float:
    return len(pcm) / (TAUX * 2)


def main() -> int:
    sys.path.insert(0, str(RACINE / "scripts"))
    import enregistrer_voix as base

    # ⚠️ Le module de base enregistre en 16 kHz pour Whisper. On impose notre
    # taux AVANT d'ouvrir le micro : le reechantillonneur est construit dans
    # `Micro._capturer`, qui lit `base.TAUX`.
    base.TAUX = TAUX

    peripherique = sys.argv[1] if len(sys.argv) > 1 else base.PERIPHERIQUE
    wavs = DOSSIER / "wavs"
    wavs.mkdir(parents=True, exist_ok=True)

    faites = _deja_faites(DOSSIER)
    restantes = [(i, t) for i, t in enumerate(CORPUS) if i not in faites]

    secondes_faites = sum(
        _duree((wavs / f"phrase-{i:04d}.wav").read_bytes()) - 44 / (TAUX * 2)
        for i in faites
        if (wavs / f"phrase-{i:04d}.wav").exists()
    )

    print(f"\nCorpus : {len(CORPUS)} phrases · {len(faites)} deja faites "
          f"(~{secondes_faites / 60:.1f} min enregistrees)")
    if not restantes:
        print("\n✓ Corpus complet. Le dossier est pret pour l'affinage :")
        print(f"    {DOSSIER}")
        return 0

    print(f"Restent : {len(restantes)} phrases\n")
    print("  Entree  = commencer, puis Entree = arreter")
    print("  « s »   = sauter cette phrase")
    print("  « q »   = arreter la seance (tout est garde)\n")
    print("  ⚠️ Reste a la MEME distance du micro pendant toute la seance,")
    print("     et arrete-toi des que ta voix fatigue. Trois seances courtes")
    print("     valent mieux qu'une longue : le modele apprendrait deux voix.\n")

    micro = base.Micro(peripherique)
    micro.ouvrir()
    if micro.erreur:
        print(f"✗ micro indisponible : {micro.erreur}")
        return 1

    try:
        for rang, (indice, texte) in enumerate(restantes, start=1):
            while True:
                print(f"\n[{rang}/{len(restantes)}]  « {texte} »")
                reponse = input("   Entree pour enregistrer > ").strip().lower()
                if reponse == "q":
                    raise KeyboardInterrupt
                if reponse == "s":
                    break

                micro.commencer()
                input("   ● enregistrement… Entree pour arreter > ")
                pcm = micro.terminer()

                if micro.erreur:
                    print(f"   ✗ micro : {micro.erreur}")
                    return 1

                duree, niveau = _duree(pcm), _rms(pcm)

                # Les trois refus possibles, chacun avec sa correction. Un
                # « recommence » sans raison ferait recommencer a l'identique.
                if duree < MIN_SECONDES:
                    print(f"   ✗ trop court ({duree:.1f} s) — parle apres avoir appuye.")
                    continue
                if duree > MAX_SECONDES:
                    print(f"   ✗ trop long ({duree:.1f} s) — arrete des la fin de la phrase.")
                    continue
                if niveau < RMS_MIN:
                    print(f"   ✗ trop faible (niveau {niveau:.3f}) — rapproche-toi du micro.")
                    continue
                if niveau > RMS_MAX:
                    print(f"   ✗ sature (niveau {niveau:.3f}) — eloigne-toi un peu.")
                    continue

                identifiant = f"phrase-{indice:04d}"
                _ecrire_wav(wavs / f"{identifiant}.wav", pcm)
                _ajouter_a_la_fiche(DOSSIER, identifiant, texte)
                secondes_faites += duree
                print(f"   ✓ {duree:.1f} s · niveau {niveau:.3f} "
                      f"· total ~{secondes_faites / 60:.1f} min")
                break
    except KeyboardInterrupt:
        print("\n\nSeance interrompue — tout ce qui est enregistre est garde.")
    finally:
        micro.fermer()

    reste = len(CORPUS) - len(_deja_faites(DOSSIER))
    print(f"\n~{secondes_faites / 60:.1f} min enregistrees · {reste} phrase(s) restante(s)")
    print(f"Dossier : {DOSSIER}")
    if secondes_faites < 15 * 60:
        print("\nIl en faut 20 a 30 minutes pour un affinage correct.")
        print("Relance le script quand tu veux : il reprend ou tu t'es arrete.")
    else:
        print("\n✓ De quoi affiner. Relance quand meme si tu veux plus de matiere :")
        print("  au-dela de trente minutes, le gain devient faible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
