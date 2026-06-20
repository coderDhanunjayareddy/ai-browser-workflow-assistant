import os
import json
import pytest

from app.adapters.amazon.adapter import AmazonAdapter
from app.adapters.gmail.adapter import GmailAdapter
from app.validators.amazon_validators import VerifyAmazonOpened, VerifySearchQueryEntered, VerifySearchResultsLoaded
from app.validators.gmail_validators import VerifyGmailOpened, VerifyComposeWindowOpened, VerifyRecipientSubjectEntered, VerifyBodyTextEntered
from app.task_graph.graph_models import TaskGraph, TaskNode

def test_amazon_adapter():
    adapter = AmazonAdapter()
    assert adapter.identify_site("https://www.amazon.com/") is True
    assert adapter.identify_site("https://www.amazon.in/") is True
    assert adapter.identify_site("https://www.google.com/") is False
    
    # Check selector map loaded from knowledge pack
    assert adapter.knowledge.get("selectors", {}).get("search_input") == "#twotabsearchtextbox"
    
    # Check validator mapping
    assert adapter.get_custom_validators("open_site") == ["verify_amazon_opened"]
    assert adapter.get_custom_validators("execute_search") == ["verify_search_results_loaded"]


def test_gmail_adapter():
    adapter = GmailAdapter()
    assert adapter.identify_site("https://mail.google.com/mail/u/0/") is True
    assert adapter.identify_site("https://gmail.com/") is True
    assert adapter.identify_site("https://makemytrip.com/") is False
    
    # Check selector map loaded from knowledge pack
    assert adapter.knowledge.get("selectors", {}).get("compose_button") == ".T-I-KE"
    
    # Check validator mapping
    assert adapter.get_custom_validators("click_compose") == ["verify_compose_window_opened"]
    assert adapter.get_custom_validators("input_body_text") == ["verify_body_text_entered"]


def test_amazon_validators():
    opened = VerifyAmazonOpened()
    # Case: Amazon URL
    res = opened.validate({"url": "https://www.amazon.in/ref=nav_logo"})
    assert res.success is True
    assert res.facts_to_add.get("site_opened") is True
    
    query = VerifySearchQueryEntered()
    # Case: search input found
    res = query.validate({"interactive_elements": [{"selector": "#twotabsearchtextbox", "type": "input"}]})
    assert res.success is True
    assert res.facts_to_add.get("search_query_entered") is True
    
    results = VerifySearchResultsLoaded()
    # Case: search query in URL
    res = results.validate({"url": "https://www.amazon.com/s?k=macbook&ref=nb_sb_noss"})
    assert res.success is True
    assert res.facts_to_add.get("results_loaded") is True


def test_gmail_validators():
    opened = VerifyGmailOpened()
    res = opened.validate({"url": "https://mail.google.com/mail/u/0/"})
    assert res.success is True
    assert res.facts_to_add.get("site_opened") is True
    
    compose = VerifyComposeWindowOpened()
    res = compose.validate({"interactive_elements": [{"placeholder": "Recipients", "aria_label": "To"}]})
    assert res.success is True
    assert res.facts_to_add.get("compose_window_opened") is True
    
    recipient = VerifyRecipientSubjectEntered()
    res = recipient.validate({"interactive_elements": [{"placeholder": "Subject", "selector": "input[name='subjectbox']"}]})
    assert res.success is True
    assert res.facts_to_add.get("recipient_subject_entered") is True
    
    body = VerifyBodyTextEntered()
    res = body.validate({"interactive_elements": [{"role": "textbox", "aria_label": "Message Body"}]})
    assert res.success is True
    assert res.facts_to_add.get("body_text_entered") is True


def test_task_graph_templates_exist():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    definitions_dir = os.path.join(base_dir, "app", "task_graph", "definitions")
    
    # Verify Amazon template file is readable JSON and can instantiate TaskGraph
    amazon_path = os.path.join(definitions_dir, "amazon_search.json")
    assert os.path.exists(amazon_path)
    with open(amazon_path, "r") as f:
        data = json.load(f)
        nodes = [TaskNode(**n) for n in data["nodes"]]
        graph = TaskGraph(graph_id=data["graph_id"], nodes=nodes)
        assert graph.graph_id == "amazon_search"
        assert len(graph.nodes) == 3

    # Verify Gmail template file is readable JSON and can instantiate TaskGraph
    gmail_path = os.path.join(definitions_dir, "gmail_draft.json")
    assert os.path.exists(gmail_path)
    with open(gmail_path, "r") as f:
        data = json.load(f)
        nodes = [TaskNode(**n) for n in data["nodes"]]
        graph = TaskGraph(graph_id=data["graph_id"], nodes=nodes)
        assert graph.graph_id == "gmail_draft"
        assert len(graph.nodes) == 4
