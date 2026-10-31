PYTHON ?= .venv/bin/python
DATABASE_URL ?= postgresql://shop:shop@localhost:5433/shop
export DATABASE_URL

.PHONY: seed test api eval web advance

seed:
	$(PYTHON) -m shop.db
	$(PYTHON) -m shop.knowledge

test:
	$(PYTHON) -m pytest

api:
	$(PYTHON) -m uvicorn shop.api:app --host 127.0.0.1 --port 8000

eval:
	$(PYTHON) -m eval.run_eval

web:
	cd web && npm run dev

# Example: make advance ORDER=ord_nima_last STATUS=confirmed
advance:
	$(PYTHON) -m shop.advance_order --order $(ORDER) --status $(STATUS) --shop tea --email admin@himali.test
