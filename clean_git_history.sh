#!/bin/bash

# Script para limpar o histórico do Git removendo commits com tokens sensíveis

echo "⚠️  ATENÇÃO: Este script irá reescrever o histórico do Git!"
echo "Certifique-se de fazer backup antes de continuar."
echo "Pressione Enter para continuar ou Ctrl+C para cancelar..."
read

# Verificar se estamos em um repositório Git
if [ ! -d ".git" ]; then
    echo "❌ Este não é um repositório Git!"
    exit 1
fi

# Fazer backup do branch atual
echo "📦 Fazendo backup do branch atual..."
git branch backup-$(date +%Y%m%d-%H%M%S)

# Remover arquivos sensíveis do histórico
echo "🧹 Removendo arquivos sensíveis do histórico..."

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
git for-each-ref --format="%(refname)" refs/original/ | xargs -n 1 git update-ref -d
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo "✅ Limpeza do histórico concluída!"
echo "📝 Lembre-se de fazer push forçado para atualizar o repositório remoto:"
echo "   git push --force-with-lease --all"
echo "   git push --force-with-lease --tags"
