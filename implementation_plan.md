# Plan d'Architecture : Backend Dédié pour Medivoc (Abonnements & API Cloud)

## 1. Contexte et Objectifs
L'objectif est de remplacer le traitement local lourd et les appels API directs depuis l'application macOS par un **Backend Cloud Dédié**. Ce backend servira d'intermédiaire sécurisé et de fondation pour le futur modèle économique :
- Cacher et gérer de manière centralisée les clés API (Deepgram, Groq, Google AI).
- Préparer l'infrastructure pour un système de **comptes utilisateurs** et **d'abonnements payants**.
- Permettre à l'utilisateur de Medivoc de choisir dynamiquement le moteur cloud de transcription (**Groq** ou **Deepgram**) à la volée.
- Traiter l'ensemble des requêtes d'intelligence artificielle via **Google AI** (Gemini).

## 2. Architecture du Backend Dédié

**Stack Technologique Recommandée** : 
- **Serveur API** : Node.js (avec Express ou NestJS) ou Python (FastAPI). Parfait pour contrôler le flux et gérer des requêtes potentiellement longues (transcription audio).
- **Base de données / Auth** : Supabase (PostgreSQL + Auth) pour gérer de façon robuste les utilisateurs, l'authentification et l'historique si nécessaire.
- **Paiements** : Stripe (pour la future gestion des abonnements, avec des webhooks reçus par le backend).

### A. Endpoint Transcription (`POST /api/v1/transcribe`)
- **Entrée** : Audio brut (WAV/M4A), Auth Token (JWT du compte utilisateur), et un paramètre `provider` (`groq` ou `deepgram`).
- **Comportement backend** :
  1. Valide le token de l'utilisateur. Vérifie s'il a un abonnement actif ou s'il lui reste des crédits de dictée.
  2. Si `provider=deepgram` : Transfère l'audio à l'API Deepgram (`nova-3` ou modèle médical).
  3. Si `provider=groq` : Transfère l'audio à l'API Groq (Whisper-large-v3, très performant et rapide).
  4. Formate le retour pour unifier la réponse JSON renvoyée à l'application macOS.
- **Sortie** : Le texte transcrit de manière unifiée, peu importe le fournisseur choisi en arrière-plan.

### B. Endpoint Traitement LLM (`POST /api/v1/process-text`)
- **Entrée** : Texte à traiter, contexte/instructions du prompt, Auth Token (JWT).
- **Comportement backend** :
  1. Vérifie les quotas ou l'abonnement en cours.
  2. Structure la requête et l'envoie à **Google AI** (ex: Gemini 1.5 Pro).
- **Sortie** : Le texte médical corrigé, mis en forme ou résumé. Gérera le modèle "Server-Sent Events" (SSE) si on a besoin de conserver l'effet "machine à écrire" dans le chat Medivoc.

--> en fait il faudrait un endpoint pour utiliser l'IA LLM "classiquement" puis en fonction de la requête on traite/utilise les données différemment.

## 3. Modifications de l'App macOS (Medivoc)

Une fois le backend en ligne, l'architecture de Medivoc va évoluer significativement :
1. **Interface Utilisateur (Auth)** : Création d'un écran d'inscription / connexion pour se lier à son compte Medivoc Cloud.
2. **Refonte du Moteur de Transcription** :
   - Mise à jour du `TranscriptionEngine` pour pointer vers votre route `/api/v1/transcribe`.
   - Ajout d'un sélecteur simple (Toggle ou bouton radio) pour choisir son proxy de transcription ("Cloud Rapide" (Groq) vs "Cloud Précis" (Deepgram)).
3. **Refonte LLM (`LLMService`)** : 
   - Remplacer les appels vers `generativelanguage.googleapis.com` par l'URL de votre propre backend.
4. **Simplification des Préférences** : Suppression des champs de saisie pour ses propres clés Gemini/Deepgram/Groq. Tout est désormais inclus dans le compte abonné.

## 4. Prochaines Étapes Prévues (Dès que l'implémentation débute)
1. **Initialisation Backend** : Création du projet serveur (Node ou Python), setup du routeur et des middlewares d'authentification.
2. **Mécanique d'APIs** : Intégration des appels Groq, Deepgram et Google AI côté serveur.
3. **Setup Base de Données** : Initialisation de Supabase pour les tables `users` et `subscriptions`.
4. **Développement Client (App)** : Ajout de la lib d'Auth dans l'app Swift, suppression des appels API externes directs et connexion au SaaS complet.


Aussi, pour il ne faut pas utilser de termes trop technique pour l'user, il faut trouver des termes plus simples et plus compréhensible pour l'user.
