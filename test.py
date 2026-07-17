from app import app; client = app.test_client(); client.set_cookie('localhost', 'session', 'test')
with client.session_transaction() as sess: sess['shrey_admin'] = True
res = client.get('/api/shrey/requests'); print(res.get_json())
