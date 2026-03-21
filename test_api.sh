#!/bin/bash

# ============================================================
#  Script de test de l'API Medivoc
#  Usage: ./test_api.sh [BASE_URL]
#  Exemple: ./test_api.sh https://medivocbackend-production.up.railway.app
# ============================================================

BASE_URL="${1:-https://medivocbackend-production.up.railway.app}"

# ── Couleurs ────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
FAIL=0

# ── Helpers ─────────────────────────────────────────────────
print_header() {
  echo ""
  echo -e "${BLUE}══════════════════════════════════════${NC}"
  echo -e "${BLUE}  $1${NC}"
  echo -e "${BLUE}══════════════════════════════════════${NC}"
}

check() {
  local name="$1"
  local status="$2"
  local expected="$3"
  local body="$4"

  if [ "$status" -eq "$expected" ]; then
    echo -e "  ${GREEN}✓${NC} $name (HTTP $status)"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}✗${NC} $name (attendu HTTP $expected, reçu HTTP $status)"
    echo -e "    ${YELLOW}Réponse:${NC} $body"
    FAIL=$((FAIL + 1))
  fi
}

# ============================================================
print_header "1. HEALTH CHECK"
# ============================================================

RESP=$(curl -s -o /tmp/body.txt -w "%{http_code}" "$BASE_URL/health")
BODY=$(cat /tmp/body.txt)
check "GET /health" "$RESP" 200 "$BODY"
echo -e "  ${YELLOW}→${NC} $BODY"

# ============================================================
print_header "2. SWAGGER DOCS"
# ============================================================

RESP=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/docs")
check "GET /docs (Swagger UI)" "$RESP" 200

RESP=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/openapi.json")
check "GET /openapi.json" "$RESP" 200

# ============================================================
print_header "3. AUTH — Sans token (doit rejeter)"
# ============================================================

RESP=$(curl -s -o /tmp/body.txt -w "%{http_code}" "$BASE_URL/auth/me")
BODY=$(cat /tmp/body.txt)
check "GET /auth/me sans token → 403" "$RESP" 403 "$BODY"

RESP=$(curl -s -o /tmp/body.txt -w "%{http_code}" "$BASE_URL/billing/status")
BODY=$(cat /tmp/body.txt)
check "GET /billing/status sans token → 403" "$RESP" 403 "$BODY"

# ============================================================
print_header "4. AUTH — Avec token invalide (doit rejeter)"
# ============================================================

FAKE_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmYWtlIn0.invalid"

RESP=$(curl -s -o /tmp/body.txt -w "%{http_code}" \
  -H "Authorization: Bearer $FAKE_TOKEN" \
  "$BASE_URL/auth/me")
BODY=$(cat /tmp/body.txt)
check "GET /auth/me avec faux token → 401" "$RESP" 401 "$BODY"

# ============================================================
print_header "5. TRANSCRIPTION — Sans token (doit rejeter)"
# ============================================================

RESP=$(curl -s -o /tmp/body.txt -w "%{http_code}" \
  -X POST \
  -F "file=@/dev/null" \
  -F "provider=groq" \
  "$BASE_URL/api/v1/transcribe")
BODY=$(cat /tmp/body.txt)
check "POST /api/v1/transcribe sans token → 403" "$RESP" 403 "$BODY"

# ============================================================
print_header "6. LLM — Sans token (doit rejeter)"
# ============================================================

RESP=$(curl -s -o /tmp/body.txt -w "%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"text":"test","instructions":""}' \
  "$BASE_URL/api/v1/process-text")
BODY=$(cat /tmp/body.txt)
check "POST /api/v1/process-text sans token → 403" "$RESP" 403 "$BODY"

RESP=$(curl -s -o /tmp/body.txt -w "%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"text":"test","instructions":""}' \
  "$BASE_URL/api/v1/process-text/stream")
BODY=$(cat /tmp/body.txt)
check "POST /api/v1/process-text/stream sans token → 403" "$RESP" 403 "$BODY"

# ============================================================
print_header "7. VALIDATION — Corps invalides"
# ============================================================

RESP=$(curl -s -o /tmp/body.txt -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer $FAKE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"","instructions":""}' \
  "$BASE_URL/api/v1/process-text")
BODY=$(cat /tmp/body.txt)
# Avec faux token on attend 401 avant même d'arriver à la validation
check "POST /api/v1/process-text texte vide + faux token → 401" "$RESP" 401 "$BODY"

# ============================================================
print_header "8. TEST AVEC JWT RÉEL (optionnel)"
# ============================================================

if [ -z "$JWT_TOKEN" ]; then
  echo -e "  ${YELLOW}⚠${NC}  Variable JWT_TOKEN non définie, tests authentifiés ignorés."
  echo -e "  ${YELLOW}→${NC}  Pour tester avec un vrai compte:"
  echo -e "     export JWT_TOKEN='votre_jwt_ici'"
  echo -e "     ./test_api.sh"
else
  echo -e "  ${GREEN}→${NC} JWT_TOKEN détecté, lancement des tests authentifiés..."

  # Auth/me
  RESP=$(curl -s -o /tmp/body.txt -w "%{http_code}" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    "$BASE_URL/auth/me")
  BODY=$(cat /tmp/body.txt)
  check "GET /auth/me avec vrai token → 200" "$RESP" 200 "$BODY"
  echo -e "  ${YELLOW}→${NC} Profil: $BODY"

  # Billing status
  RESP=$(curl -s -o /tmp/body.txt -w "%{http_code}" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    "$BASE_URL/billing/status")
  BODY=$(cat /tmp/body.txt)
  check "GET /billing/status avec vrai token → 200" "$RESP" 200 "$BODY"
  echo -e "  ${YELLOW}→${NC} Statut: $BODY"

  # LLM sync
  RESP=$(curl -s -o /tmp/body.txt -w "%{http_code}" \
    -X POST \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"text":"patient avec douleur thoracique depuis 2 jours","instructions":"Corrige et formate ce texte médical en français","model":"gemini-2.0-flash"}' \
    "$BASE_URL/api/v1/process-text")
  BODY=$(cat /tmp/body.txt)
  check "POST /api/v1/process-text → 200" "$RESP" 200 "$BODY"
  echo -e "  ${YELLOW}→${NC} Résultat LLM: $BODY"

  # LLM streaming
  echo -e "  ${YELLOW}→${NC} Test streaming SSE..."
  curl -s \
    -X POST \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"text":"fièvre 38.5 depuis hier soir","instructions":"Formate en phrase médicale","model":"gemini-2.0-flash"}' \
    --no-buffer \
    "$BASE_URL/api/v1/process-text/stream" | head -20
  echo ""
  PASS=$((PASS + 1))

  # Transcription (audio de test)
  if command -v ffmpeg &>/dev/null; then
    ffmpeg -f lavfi -i "sine=frequency=440:duration=2" /tmp/test_audio.wav -y -loglevel quiet
    RESP=$(curl -s -o /tmp/body.txt -w "%{http_code}" \
      -X POST \
      -H "Authorization: Bearer $JWT_TOKEN" \
      -F "file=@/tmp/test_audio.wav" \
      -F "provider=groq" \
      "$BASE_URL/api/v1/transcribe")
    BODY=$(cat /tmp/body.txt)
    check "POST /api/v1/transcribe (audio généré) → 200" "$RESP" 200 "$BODY"
    echo -e "  ${YELLOW}→${NC} Transcription: $BODY"
    rm -f /tmp/test_audio.wav
  else
    echo -e "  ${YELLOW}⚠${NC}  ffmpeg non installé, test transcription ignoré."
    echo -e "     Installe ffmpeg ou fournis un fichier audio manuellement."
  fi
fi

# ============================================================
print_header "RÉSULTATS"
# ============================================================

TOTAL=$((PASS + FAIL))
echo ""
echo -e "  Tests réussis : ${GREEN}$PASS${NC} / $TOTAL"
if [ "$FAIL" -gt 0 ]; then
  echo -e "  Tests échoués : ${RED}$FAIL${NC} / $TOTAL"
fi
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}✓ Tous les tests sont passés !${NC}"
  exit 0
else
  echo -e "${RED}✗ $FAIL test(s) en échec.${NC}"
  exit 1
fi
