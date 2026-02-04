# Configuração de Segurança

## ⚠️ Tokens Sensíveis Removidos

Os seguintes tokens sensíveis foram removidos dos arquivos de configuração:

- **Discord Token**: Removido de `config.json`
- **JWT Tokens**: Removidos de `cookies.json`
- **GamersClub Session**: Removida de `cookies.json`

## 🔧 Configuração de Variáveis de Ambiente

### 1. Criar arquivo .env

Copie o arquivo `env.template` para `.env`:

```bash
cp env.template .env
```

### 2. Configurar variáveis

Edite o arquivo `.env` com seus tokens reais:

```env
# Discord Bot Configuration
DISCORD_TOKEN=seu_token_discord_aqui

# OpenAI Configuration
OPENAI_API_KEY=sua_chave_openai_aqui

# GamersClub Configuration
GAMERSCLUB_ACCESS_TOKEN=seu_token_gamersclub_aqui
GAMERSCLUB_SESSION_COOKIE=seu_cookie_sessao_aqui
```

### 3. Atualizar código para usar variáveis de ambiente

O código precisa ser atualizado para ler as variáveis do arquivo `.env` em vez dos arquivos de configuração hardcoded.

## 🧹 Limpeza do Histórico Git

Para remover completamente os tokens do histórico do Git, execute:

```bash
./clean_git_history.sh
```

**⚠️ ATENÇÃO**: Este script irá reescrever o histórico do Git. Faça backup antes de executar!

## 📋 Checklist de Segurança

- [x] Tokens removidos de `config.json`
- [x] JWT tokens removidos de `cookies.json`
- [x] Arquivo `.env` adicionado ao `.gitignore`
- [x] Template de variáveis criado (`env.template`)
- [ ] Código atualizado para usar variáveis de ambiente
- [ ] Histórico Git limpo (opcional)

## 🔒 Boas Práticas

1. **Nunca commite** arquivos `.env` ou tokens sensíveis
2. **Use variáveis de ambiente** para todos os tokens
3. **Faça backup** antes de limpar o histórico Git
4. **Teste** o bot após as alterações
5. **Monitore** logs para erros de autenticação
