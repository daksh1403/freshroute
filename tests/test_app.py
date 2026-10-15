from streamlit.testing.v1 import AppTest


def test_dashboard_runs_solver_and_disruption():
    app = AppTest.from_file('../app.py',default_timeout=30).run()
    assert not app.exception
    app.button(key='generate').click().run()
    assert not app.exception
    assert any('21,123' in m.value for m in app.metric)
    app.slider(key='delay').set_value(6.0)
    app.button(key='replan').click().run()
    assert not app.exception
    assert any('infeasible' in w.value.lower() for w in app.warning)
