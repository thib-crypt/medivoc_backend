# Documentation API Medivoc Backend

> **Version** : 1.0.0  
> **Base URL (prod)** : `https://medivocbackend-production.up.railway.app`  
> **Base URL (local)** : `http://localhost:8000`  
> **Authentification** : JWT Supabase (Bearer token)  

---

## Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Authentification](#authentification)
3. [Endpoints](#endpoints)
   - [Authentification](#authentification-1)
   - [Transcription](#transcription)
   - [Traitement LLM](#traitement-llm)
   - [Billing](#billing)
   - [Santé](#santé)
4. [Codes d'erreur](#codes-derreur)
5. [Exemples d'utilisation](#exemples-dutilisation)
6. [Déploiement](#déploiement)

---

## Vue d'ensemble

L'API Medivoc fournit :
- **Transcription audio** via Groq (Whisper) ou Deepgram (Nova-3)
- **Traitement LLM** via Google Gemini (sync + streaming SSE)
- **Gestion des quotas** par utilisateur (Free = 30 min/mois, Pro = illimité)
- **Authentification sécurisée** via Supabase Auth

---

## Authentification

### Comment obtenir un JWT token

1. **Via l'app Supabase Auth** (recommandé) :
```javascript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  'https://aahlawqwgvyfpqgyhzot.supabase.co',
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFhaGxhd3F3Z3Z5ZnBxZ3loem90Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM1NDg0NTQsImV4cCI6MjA4OTEyNDQ1NH0.PHbsVKrMXcsRrffs5K5PVI9KBA0SETQlauaExcxan9o'
)

const { data, error } = await supabase.auth.signInWithPassword({
  email: 'user@example.com',
  password: 'password'
})

const jwt = data.session.access_token
```

2. **Utilisation dans les requêtes** :
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
     https://medivocbackend-production.up.railway.app/auth/me
```

---

## Endpoints

### Authentification

#### `GET /auth/me`
Récupère les informations de l'utilisateur connecté.

**Headers requis**
- `Authorization: Bearer <JWT_TOKEN>`

**Réponse (200 OK)**
```json
{
  "id": "uuid-string",
  "email": "user@example.com",
  "plan": "free",
  "minutes_used_this_month": 12.5,
  "quota_reset_at": "2026-04-01T00:00:00Z"
}
```

---

### Transcription

#### `POST /api/v1/transcribe`
Transcrit un fichier audio (WAV/M4A/MP3) en texte.

**Headers requis**
- `Authorization: Bearer <JWT_TOKEN>`
- `Content-Type: multipart/form-data`

**Body (form-data)**
| Champ | Type | Requis | Description |
|---|---|---|---|
| `file` | File | ✅ | Fichier audio (WAV/M4A/MP3) |
| `provider` | String | ❌ | `groq` (défaut) ou `deepgram` |

**Réponse (200 OK)**
```json
{
  "text": "Le patient présente des douleurs thoraciques...",
  "provider": "groq",
  "duration_seconds": 12.5
}
```

**Erreurs**
- `400` : Fichier vide ou provider invalide
- `401` : Token invalide ou expiré
- `402` : Quota dépassé (plan Free : 30 min/mois)
- `403` : Token absent (header Authorization manquant)
- `502` : Erreur du service de transcription (Groq/Deepgram)

**Exemple cURL**
```bash
curl -X POST \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -F "file=@audio.wav" \
  -F "provider=groq" \
  https://medivocbackend-production.up.railway.app/api/v1/transcribe
```

---

### Traitement LLM

#### `POST /api/v1/process-text`
Traite un texte avec Gemini (synchrone).

**Headers requis**
- `Authorization: Bearer <JWT_TOKEN>`
- `Content-Type: application/json`

**Body**
```json
{
  "text": "patient avec douleur thoracique",
  "instructions": "Corrige et formate ce texte médical",
  "model": "gemini-2.0-flash"
}
```

**Réponse (200 OK)**
```json
{
  "result": "Patient présentant des douleurs thoraciques..."
}
```

#### `POST /api/v1/process-text/stream`
Traite un texte avec Gemini (streaming SSE).

**Headers requis**
- `Authorization: Bearer <JWT_TOKEN>`
- `Content-Type: application/json`

**Body** : Identique à la version synchrone

**Réponse (SSE)**
```
data: {"chunk": "Patient"}

data: {"chunk": " présentant"}

data: {"chunk": " des"}

data: {"chunk": " douleurs"}

data: [DONE]
```

**Erreurs communes**
- `400` : Texte vide
- `401` : Token invalide ou expiré
- `403` : Token absent
- `502` : Erreur du service Gemini

**Exemple JavaScript (streaming)**
```javascript
const response = await fetch('/api/v1/process-text/stream', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    text: 'patient avec douleur',
    instructions: 'Corrige ce texte'
  })
})

const reader = response.body.getReader()
const decoder = new TextDecoder()

while (true) {
  const { done, value } = await reader.read()
  if (done) break
  
  const chunk = decoder.decode(value)
  if (chunk.includes('[DONE]')) break
  
  const match = chunk.match(/data: ({.+})/)
  if (match) {
    const data = JSON.parse(match[1])
    console.log(data.chunk) // Texte en temps réel
  }
}
```

---

### Billing

#### `GET /billing/status`
Récupère le statut de l'abonnement et l'utilisation.

**Headers requis**
- `Authorization: Bearer <JWT_TOKEN>`

**Réponse (200 OK)**
```json
{
  "plan": "free",
  "minutes_used_this_month": 12.5,
  "quota_reset_at": "2026-04-01T00:00:00Z",
  "stripe_configured": false
}
```

---

### Santé

#### `GET /health`
Vérifie que l'API fonctionne.

**Réponse (200 OK)**
```json
{
  "status": "ok",
  "service": "medivoc-api"
}
```

---

## Codes d'erreur

| Code | Signification | Description |
|---|---|---|
| `200` | OK | Succès |
| `400` | Bad Request | Requête invalide (paramètres manquants, etc.) |
| `401` | Unauthorized | JWT invalide ou expiré |
| `402` | Payment Required | Quota dépassé (plan Free) |
| `404` | Not Found | Ressource introuvable |
| `422` | Unprocessable Entity | Validation des données échouée |
| `502` | Bad Gateway | Erreur d'un service externe (Groq/Deepgram/Gemini) |
| `500` | Internal Server Error | Erreur serveur interne |

**Format des erreurs**
```json
{
  "detail": "Message d'erreur explicatif"
}
```

---

## Exemples d'utilisation

### Workflow complet (transcription + traitement)

```bash
# 1. S'authentifier (via app Supabase)
JWT="<your_jwt_token>"

# 2. Transcrire un audio
TRANSCRIBE_RESULT=$(curl -s -X POST \
  -H "Authorization: Bearer $JWT" \
  -F "file=@consultation.wav" \
  -F "provider=groq" \
  https://medivocbackend-production.up.railway.app/api/v1/transcribe)

# Extraire le texte transcrit
TEXT=$(echo $TRANSCRIBE_RESULT | jq -r '.text')

# 3. Traiter le texte avec Gemini
curl -X POST \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"$TEXT\",\"instructions\":\"Corrige et structure ce rapport médical\"}" \
  https://medivocbackend-production.up.railway.app/api/v1/process-text
```

### Monitoring de l'utilisation

```bash
# Vérifier son quota restant
curl -H "Authorization: Bearer $JWT" \
     https://medivocbackend-production.up.railway.app/billing/status
```

---

## Déploiement

### Railway (recommandé)

1. **Connecter le repo GitHub** à Railway
2. **Variables d'environnement** (dans Railway) :
```env
SUPABASE_URL=https://aahlawqwgvyfpqgyhzot.supabase.co
SUPABASE_SERVICE_KEY=votre_service_role_key
GROQ_API_KEY=votre_groq_key
DEEPGRAM_API_KEY=votre_deepgram_key
GEMINI_API_KEY=votre_gemini_key
```

3. **Déployer** : Railway détecte automatiquement le `Dockerfile`

### Docker local

```bash
docker build -t medivoc-backend .
docker run -p 8000:8000 \
  -e SUPABASE_URL=... \
  -e SUPABASE_SERVICE_KEY=... \
  -e GROQ_API_KEY=... \
  -e DEEPGRAM_API_KEY=... \
  -e GEMINI_API_KEY=... \
  medivoc-backend
```

### Développement local

```bash
# Installer les dépendances
pip install -r requirements.txt

# Créer le .env à partir de .env.example
cp .env.example .env
# Éditer .env avec vos vraies clés

# Démarrer le serveur
uvicorn app.main:app --reload
```

---

## Limites et quotas

| Plan | Transcription | LLM | Prix |
|---|---|---|---|
| **Free** | 30 minutes/mois | ✅ Illimité | Gratuit |
| **Pro** | Illimité | ✅ Illimité | À définir |

- Le quota de transcription se **réinitialise le 1er de chaque mois**
- Les requêtes LLM ne sont **pas limitées** (même en plan Free)
- Le streaming SSE est **disponible pour tous les plans**

---

## Intégration Swift / macOS (app Medivoc)

### Configuration de base
```swift
let baseURL = "https://medivocbackend-production.up.railway.app"
let supabaseURL = "https://aahlawqwgvyfpqgyhzot.supabase.co"
let supabaseAnonKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFhaGxhd3F3Z3Z5ZnBxZ3loem90Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM1NDg0NTQsImV4cCI6MjA4OTEyNDQ1NH0.PHbsVKrMXcsRrffs5K5PVI9KBA0SETQlauaExcxan9o"
```

### Authentification (Supabase Swift SDK)
```swift
import Supabase

let supabase = SupabaseClient(supabaseURL: URL(string: supabaseURL)!, supabaseKey: supabaseAnonKey)

// Connexion
let session = try await supabase.auth.signIn(email: email, password: password)
let jwt = session.accessToken
```

### Requête type avec JWT
```swift
var request = URLRequest(url: URL(string: "\(baseURL)/auth/me")!)
request.setValue("Bearer \(jwt)", forHTTPHeaderField: "Authorization")
let (data, _) = try await URLSession.shared.data(for: request)
```

### Transcription audio
```swift
var request = URLRequest(url: URL(string: "\(baseURL)/api/v1/transcribe")!)
request.httpMethod = "POST"
request.setValue("Bearer \(jwt)", forHTTPHeaderField: "Authorization")

let boundary = UUID().uuidString
request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

var body = Data()
body.append("--\(boundary)\r\n".data(using: .utf8)!)
body.append("Content-Disposition: form-data; name=\"provider\"\r\n\r\ngroq\r\n".data(using: .utf8)!)
body.append("--\(boundary)\r\n".data(using: .utf8)!)
body.append("Content-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\n".data(using: .utf8)!)
body.append("Content-Type: audio/wav\r\n\r\n".data(using: .utf8)!)
body.append(audioData)
body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
request.httpBody = body

let (data, _) = try await URLSession.shared.data(for: request)
let result = try JSONDecoder().decode(TranscribeResponse.self, from: data)
print(result.text)
```

### Structures Swift attendues
```swift
struct TranscribeResponse: Codable {
    let text: String
    let provider: String
    let durationSeconds: Double
    
    enum CodingKeys: String, CodingKey {
        case text, provider
        case durationSeconds = "duration_seconds"
    }
}

struct ProcessTextResponse: Codable {
    let result: String
}

struct BillingStatus: Codable {
    let plan: String
    let minutesUsedThisMonth: Double
    let quotaResetAt: String
    let stripeConfigured: Bool
    
    enum CodingKeys: String, CodingKey {
        case plan
        case minutesUsedThisMonth = "minutes_used_this_month"
        case quotaResetAt = "quota_reset_at"
        case stripeConfigured = "stripe_configured"
    }
}

struct APIError: Codable {
    let detail: String
}
```

### Gestion des erreurs
```swift
switch response.statusCode {
case 200: // Succès
case 401: // Token expiré → relancer auth.refreshSession()
case 402: // Quota dépassé → afficher message upgrade
case 403: // Token manquant → rediriger vers login
case 502: // Erreur service externe → afficher message d'erreur
default: break
}
```

---

## Support et monitoring

- **Health check** : `GET /health`
- **Documentation interactive** : `/docs` (Swagger UI)
- **OpenAPI schema** : `/openapi.json`

Pour toute question technique ou bug, créer une issue sur le repo GitHub :  
https://github.com/thib-crypt/medivoc_backend/issues
