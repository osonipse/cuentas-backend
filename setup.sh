#!/bin/bash
# Cuentas Backend · Setup — compatible Python 3.9-3.14
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "${GREEN}"
echo "╔══════════════════════════════════════════╗"
echo "║   Cuentas Backend · Setup               ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# ── 1. Python ──
echo -e "${BLUE}→ Verificando Python...${NC}"
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3.13 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        echo -e "   Encontrado: $cmd ($VER)"
        PYTHON="$cmd"; break
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${RED}✗ Python no encontrado.${NC}"; exit 1
fi
echo -e "${GREEN}✓ Usando: $PYTHON ($VER)${NC}"

# ── 2. Dependencias ──
echo -e "${BLUE}→ Instalando dependencias...${NC}"
"$PYTHON" -m pip install --upgrade pip -q 2>/dev/null || true
"$PYTHON" -m pip install \
    "fastapi==0.115.0" \
    "uvicorn==0.30.0" \
    "httpx==0.27.0" \
    "python-jose[cryptography]==3.3.0" \
    "cryptography==42.0.0" \
    "python-dotenv==1.0.0" \
    "pydantic==1.10.21" \
    -q 2>&1 | grep -v "^$" | grep -v "already satisfied" | grep -v "WARNING" || true
echo -e "${GREEN}✓ Dependencias instaladas${NC}"

# ── 3. Clave RSA ──
if [ ! -f "private_key.pem" ]; then
    echo -e "${BLUE}→ Generando par de claves RSA...${NC}"
    openssl genrsa -out private_key.pem 2048 2>/dev/null
    openssl rsa -in private_key.pem -pubout -out public_key.pem 2>/dev/null
    echo -e "${GREEN}✓ Claves generadas: private_key.pem / public_key.pem${NC}"
    echo ""
    echo -e "${YELLOW}  PASO SIGUIENTE: sube public_key.pem a Enablebanking${NC}"
    echo -e "  1. enablebanking.com/sign-in/ → entra con tu email"
    echo -e "  2. API Applications → New Application"
    echo -e "  3. Sube public_key.pem"
    echo -e "  4. Copia el Application ID"
else
    echo -e "${GREEN}✓ Claves ya existen${NC}"
fi

# ── 4. .env ──
if [ ! -f ".env" ]; then
    cp env.example .env 2>/dev/null || cp .env.example .env 2>/dev/null || true
    echo ""
    echo -e "${YELLOW}  Edita .env con tu Application ID:${NC}"
    echo -e "  nano .env   (o abre el archivo con cualquier editor)"
else
    echo -e "${GREEN}✓ .env ya existe${NC}"
fi

echo ""
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup completado ✓${NC}"
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo ""
echo -e "Próximos pasos:"
echo -e "  1. Edita .env con tu EB_APP_ID"
echo -e "  2. ${BLUE}python3 main.py${NC}"
echo -e "  3. Abre ${BLUE}http://localhost:8000${NC}"
echo ""
