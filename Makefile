.PHONY: install install-skill install-extension test lint

install: install-skill install-extension

install-skill:
	mkdir -p ~/.claude/commands
	ln -sf $(CURDIR)/commands/prefxplain.md ~/.claude/commands/prefxplain.md
	@echo "Installed Claude Code command: /prefxplain"

install-extension:
	@cd $(CURDIR)/prefxplain-vscode && npm install --silent 2>/dev/null && npm run compile 2>/dev/null && npx @vscode/vsce package --allow-missing-repository 2>/dev/null
	@IDE_CLI=$$(which code 2>/dev/null || which cursor 2>/dev/null || which windsurf 2>/dev/null \
		|| ([ -x "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" ] && echo "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code") \
		|| echo ""); \
	if [ -n "$$IDE_CLI" ]; then \
		$$IDE_CLI --install-extension $(CURDIR)/prefxplain-vscode/prefxplain-vscode-0.1.0.vsix --force 2>/dev/null; \
		echo "Installed prefxplain-vscode extension via $$IDE_CLI"; \
	else \
		echo "No IDE CLI found. Install manually: code --install-extension $(CURDIR)/prefxplain-vscode/prefxplain-vscode-0.1.0.vsix"; \
	fi

test: test-py test-js

test-py:
	python -m pytest tests/ -x -q

test-js:
	node --test tests/*.mjs

lint:
	ruff check prefxplain/ tests/
