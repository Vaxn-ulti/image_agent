from app.services.compat import legacy


def health():
    return legacy().health()


def list_workflows():
    return legacy().list_workflows()


def get_result_contract():
    return legacy().get_result_contract()


def deployment():
    return legacy().deployment()


def agent_rag_status():
    return legacy().agent_rag_status()


def agent_rag_rebuild():
    return legacy().agent_rag_rebuild()


def agent_model_status():
    return legacy().agent_model_status()


def agent_run(req):
    return legacy().agent_run(req)


def agent_run_lookup(agent_run_id):
    return legacy().agent_run_lookup(agent_run_id)


def agent_resume(thread_id, req):
    return legacy().agent_resume(thread_id, req)


def agent_rag_query(req):
    return legacy().agent_rag_query(req)


def agent_verify_scientific_reports(req):
    return legacy().agent_verify_scientific_reports(req)


def runtime_containers():
    return legacy().runtime_containers()


def admin_containers():
    return legacy().admin_containers()


def list_project_agent_run_history(project_id):
    return legacy().list_project_agent_run_history(project_id)


def chat(req):
    return legacy().chat(req)
