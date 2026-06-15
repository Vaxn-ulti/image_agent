from app.services.compat import legacy


def list_project_tasks(project_id):
    return legacy().list_project_tasks(project_id)


def get_series(series_id):
    return legacy().get_series(series_id)


def validate_run_request(series, req):
    return legacy().validate_run_request(series, req)


def create_series_task(series_id, req):
    return legacy().create_series_task(series_id, req)


def run_series(series_id, req):
    return legacy().run_series(series_id, req)


def get_task(task_id):
    return legacy().get_task(task_id)
