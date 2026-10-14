backend:
	cd backend && uvicorn app.main:app --reload
test:
	cd backend && pytest -q

