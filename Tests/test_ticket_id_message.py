from App.integration.iengage.client import IEngageClient
def test_incident_id_is_extracted_from_message():
    body={'Message':'Request saved successfully. 107723_INC000107723'}
    assert IEngageClient._extract_ticket_id_from_message(body)=='INC000107723'
