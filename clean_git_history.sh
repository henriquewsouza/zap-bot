#!/bin/bash

# Script para limpar o histórico do Git removendo commits com tokens sensíveis

set -euo pipefail

YES=false
if [[ "${1:-}" == "--yes" ]]; then
    YES=true
fi

echo "⚠️  ATENÇÃO: Este script irá reescrever o histórico do Git!"
echo "Certifique-se de fazer backup antes de continuar."
if [[ "$YES" != "true" ]]; then
    echo "Para continuar, execute: ./clean_git_history.sh --yes"
    exit 2
fi

# Verificar se estamos em um repositório Git
if [ ! -d ".git" ]; then
    echo "❌ Este não é um repositório Git!"
    exit 1
fi

# Fazer backup do branch atual
echo "📦 Fazendo backup do branch atual..."
git branch backup-$(date +%Y%m%d-%H%M%S)

# Remover arquivos sensíveis do histórico
echo "🧹 Removendo arquivos sensíveis do histórico (cookies.json, config.json)..."

# Remover cookies.json do histórico
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch cookies.json' \
  --prune-empty --tag-name-filter cat -- --all

# Remover config.json do histórico (se contiver tokens)
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch config.json' \
  --prune-empty --tag-name-filter cat -- --all

# Limpar referências órfãs
echo "🧽 Limpando referências órfãs..."

# Remover refs/original/* sem depender de xargs (mais robusto em ambientes restritos)
while IFS= read -r ref; do
    if [[ -n "${ref}" ]]; then
        git update-ref -d "${ref}" || true
    fi
done < <(git for-each-ref --format="%(refname)" refs/original/ || true)

git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo "✅ Limpeza do histórico concluída!"
echo "📝 Lembre-se de fazer push forçado para atualizar o repositório remoto:"
echo "   git push --force-with-lease --all"
echo "   git push --force-with-lease --tags"
