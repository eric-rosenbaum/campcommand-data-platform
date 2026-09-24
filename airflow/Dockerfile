FROM apache/airflow:3.3.2-python3.12

# The pipeline and dbt get their own virtualenv so their dependency pins
# can't collide with Airflow's. Python tasks run in it through
# @task.external_python.
USER root
COPY pyproject.toml /opt/campcommand/pyproject.toml
COPY src /opt/campcommand/src
COPY warehouse/dbt_project.yml warehouse/packages.yml /opt/campcommand/deps/
RUN python -m venv /opt/campcommand/venv \
    && /opt/campcommand/venv/bin/pip install --no-cache-dir /opt/campcommand \
    && ln -s /opt/campcommand/venv/bin/dbt /usr/local/bin/dbt \
    && ln -s /opt/campcommand/venv/bin/campcommand /usr/local/bin/campcommand \
    && DBT_PACKAGES_INSTALL_PATH=/opt/campcommand/dbt_packages \
       /opt/campcommand/venv/bin/dbt deps --project-dir /opt/campcommand/deps \
    && chown -R airflow: /opt/campcommand
USER airflow

ENV DBT_PACKAGES_INSTALL_PATH=/opt/campcommand/dbt_packages
