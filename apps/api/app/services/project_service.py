from app.services.compat import legacy


def login(req):
    return legacy().login(req)


def list_projects():
    return legacy().list_projects()


def create_project(req):
    return legacy().create_project(req)
