# TechAdmin
IT for Internal System
TechAdmin Agent Platform - Version 1 (Password Reset MVP) 

Objective: Build an end-to-end flow for Password Reset using Intent Classification, Metadata Extraction, Agent Routing, API Execution and Response Handling. 

techadmin-agent/ 

 

│ 

 

├── README.md 

 

├── requirements.txt 

 

├── .env 

 

├── .gitignore 

 

│ 

 

├── app/ 

 

│ │ 

 

│ ├── main.py # FastAPI Entry Point 

 

│ │ 

 

│ ├── api/ 

 

│ │ ├── routes.py 

 

│ │ └── schemas.py 

 

│ │ 

 

│ ├── agents/ 

 

│ │ ├── identity_agent.py 

 

│ │ ├── network_agent.py 

 

│ │ └── patch_agent.py 

 

│ │ 

 

│ ├── workflows/ 

 

│ │ ├── router.py 

 

│ │ ├── graph.py 

 

│ │ └── state.py 

 

│ │ 

 

│ ├── intent/ 

 

│ │ ├── classifier.py 

 

│ │ ├── metadata_extractor.py 

 

│ │ └── prompts.py 

 

│ │ 

 

│ ├── tools/ 

 

│ │ ├── identity/ 

 

│ │ │ └── reset_password.py 

 

│ │ │ 

 

│ │ ├── network/ 

 

│ │ └── patch/ 

 

│ │ 

 

│ ├── integrations/ 

 

│ │ ├── identity_api.py 

 

│ │ ├── auth.py 

 

│ │ └── api_client.py 

 

│ │ 

 

│ ├── models/ 

 

│ │ └── request_models.py 

 

│ │ 

 

│ └── utils/ 

 

│ ├── logger.py 

 

│ └── config.py 

 

│ 

 

├── tests/ 

 

│ ├── test_intent.py 

 

│ ├── test_agent.py 

 

│ └── test_api.py 

 

│ 

 

├── docs/ 

 

│ ├── Architecture.docx 

 

│ ├── Requirements.xlsx 

 

│ ├── WBS.xlsx 

 

│ └── API_Inventory.xlsx 

 

│ 

 

├── sample_requests/ 

 

│ └── password_reset.json 

 

│ 

 

└── scripts/ 

 

├── setup_env.bat 

 

└── run_local.bat 

 

 

 

TechAdmin Agent Platform - V1 Solution Overview & Team Responsibilities 

1. Project Overview 

Objective 

The objective of the TechAdmin Agent Platform is to automate repetitive IT operational tasks by leveraging AI agents and enterprise APIs. 

Instead of IT teams manually processing requests such as password resets, account unlocks, and access provisioning, users will be able to submit requests through Teams/Copilot, and the platform will automatically execute the required actions through approved APIs. 

 

2. Version 1 Scope 

Initial Use Case 

Password Reset 

The objective of Version 1 is to establish a reusable framework that will later support all TechAdmin use cases. 

Future Use Cases 

Identity 

Password Reset 

Account Unlock 

Grant/Revoke Access 

Network 

Guest WiFi Access 

Connectivity Checks 

Network Diagnostics 

Patch & Configuration 

Software Installation 

Patch Management 

Restart Services 

 

3. Solution Architecture 

Version 1 Architecture 

User Request 
 

↓ 
 

FastAPI Endpoint 
 

↓ 
 

Intent Classification 
 

↓ 
 

Metadata Extraction 
 

↓ 
 

Router 
 

↓ 
 

Identity Agent 
 

↓ 
 

Password Reset Tool 
 

↓ 
 

Password Reset API 
 

↓ 
 

Response Formatter 
 

↓ 
 

Success / Failure Response 

Example Flow 

User Input: 

Reset password for aman.gupta 

Structured Output: 

{ 
 

"intent": "password_reset", 
 

"username": "aman.gupta" 
 

} 

Execution: 

Identity Agent 
 

↓ 
 

Password Reset Tool 
 

↓ 
 

Password Reset API 

Output: 

Password reset completed successfully. 

 

4. Component Description 

FastAPI 

Acts as the entry point for all requests. 

Responsibilities: 

Receive user requests 

Invoke LangGraph workflow 

Return final response 

Ollama 

Hosts local LLM models. 

Responsibilities: 

Intent understanding 

Metadata extraction 

Routing assistance 

LangGraph 

Orchestrates the entire workflow. 

Responsibilities: 

Intent Routing 

Agent Execution 

Process Flow Management 

Intent Classifier 

Identifies the type of request. 

Examples: 

Password Reset 

Account Unlock 

Software Installation 

Metadata Extractor 

Extracts: 

Username 

User ID 

Email ID 

Employee Number 

Router 

Routes requests to the appropriate agent. 

Identity Agent 

Executes identity-related operations. 

Tool Layer 

Interfaces with enterprise APIs. 

Password Reset API 

Performs the actual password reset operation. 

Response Formatter 

Converts technical outputs into user-friendly responses. 

 

5. Team Responsibilities 

Aman Gupta (Tech Lead) 

Responsibilities: 

Requirement Gathering 

Architecture Design 

Sprint Planning 

Stakeholder Communication 

Task Allocation 

Review & Governance 

Roadmap Planning 

Deliverables: 

Architecture Documents 

WBS 

Project Roadmap 

Demo Reviews 

 

AI Engineer – Amit Bhagat 

Module Owner: Intent Classification & Metadata Extraction 

Responsibilities: 

Intent Classification 

Prompt Development 

Metadata Extraction 

Validation Logic 

LangGraph Intent Node 

Deliverables: 

Intent Classifier 

Extraction Logic 

Prompt Templates 

 

AI Engineer - Shreesanyog 

Module Owner: Agent Framework & Orchestration 

Responsibilities: 

LangGraph Setup 

Agent Development 

Router Development 

Response Formatting 

Workflow Orchestration 

Deliverables: 

Identity Agent 

Routing Logic 

End-to-End Workflow 

 

IT Developer – Aman Mishra 

Module Owner: API Integration 

Responsibilities: 

API Analysis 

Authentication Setup 

API Wrapper Development 

Error Handling 

Deliverables: 

Password Reset API Client 

Authentication Framework 

Tool Interface 

 

IT Developer - Roshan 

Module Owner: FastAPI & Testing 

Responsibilities: 

FastAPI Development 

Endpoint Creation 

Functional Testing 

Integration Testing 

Deliverables: 

Backend Service 

Test Reports 

End-to-End Validation 

 

6. Future Architecture 

Router 
 

│ 
 

├── Identity Agent 
 

│ ├── Password Reset 
 

│ ├── Account Unlock 
 

│ └── Grant Access 
 

│ 
 

├── Network Agent 
 

│ ├── Guest WiFi 
 

│ └── Connectivity Check 
 

│ 
 

└── Patch Agent 
 

├── Software Install 
 

└── Patch Management 

 

8. Expected Outcomes 

Current State 

User 
 

↓ 
 

IT Team 
 

↓ 
 

Manual Processing 
 

↓ 
 

Response 
 

`` 

Future State 

User 
 

↓ 
 

TechAdmin Agent 
 

↓ 
 

API Execution 
 

↓ 
 

Response 

Benefits 

Reduced manual effort 

Faster ticket resolution 

Standardized execution 

Improved auditability 

Reusable automation framework 

Scalable architecture for future use cases 

 

9. Success Criteria 

Version 1 will be considered successful when: 

✅ Password Reset requests are identified correctly 

✅ Required user information is extracted correctly 

✅ Password Reset API is invoked successfully 

✅ Appropriate response is returned 

✅ End-to-end workflow operates without manual intervention 

✅ Architecture is reusable for future TechAdmin use cases 

 

 

 

 

 

 

 

 

 

 

 

 

 

 

 

 

 

 

 

 

 

 

 

 

 