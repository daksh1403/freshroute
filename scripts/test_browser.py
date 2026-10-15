"""Real-browser acceptance test against a built/served browser app."""
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright, expect

url=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8788'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1050},accept_downloads=True)
    errors=[]
    page.on('pageerror',lambda err:errors.append(str(err)))
    page.goto(url,wait_until='domcontentloaded')
    expect(page.locator('#generate')).to_be_enabled(timeout=300000)
    page.locator('#generate').click()
    expect(page.locator('#net-revenue')).to_contain_text('21,123',timeout=60000)
    expect(page.locator('#violations')).to_have_text('0')
    page.screenshot(path='/tmp/freshroute-overview.png',full_page=True)
    page.locator('[data-tab="plan"]').click()
    expect(page.locator('#shipment-table')).to_contain_text('T-101')
    page.locator('[data-tab="disruptions"]').click()
    page.locator('#replan').click()
    expect(page.locator('#disruption-results')).to_contain_text('Previous plan is infeasible',timeout=60000)
    expect(page.locator('#disruption-results')).to_contain_text('0 constraint violations')
    page.locator('[data-tab="reports"]').click()
    with page.expect_download() as info: page.locator('[data-kind="report"]').click()
    download=info.value
    report=json.loads(Path(download.path()).read_text())
    assert abs(report['optimized_metrics']['net_revenue']-21123)<1e-5
    assert report['optimized_metrics']['constraint_violations']==[]
    # Spreadsheet import executes the real pure-Python parser in the worker.
    import pandas as pd
    with pd.ExcelWriter('/tmp/freshroute-browser-input.xlsx') as writer:
        for key,value in report['scenario'].items():
            pd.DataFrame([value] if key=='config' else value).to_excel(writer,sheet_name=key,index=False)
    page.locator('#upload').set_input_files('/tmp/freshroute-browser-input.xlsx')
    expect(page.locator('#runtime-status')).to_contain_text('Validated',timeout=60000)
    expect(page.locator('#net-revenue')).to_have_text('—')
    expect(page.locator('#error')).to_be_hidden()
    page.locator('#generate').click()
    expect(page.locator('#net-revenue')).to_contain_text('21,123',timeout=60000)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path='/tmp/freshroute-mobile.png',full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile page overflows horizontally'
    assert not errors,errors
    print(json.dumps({'url':url,'browser':'Chrome','net_revenue':report['optimized_metrics']['net_revenue'],
                      'constraint_violations':0,'disruption':'passed','downloads':'passed','xlsx_import':'passed','mobile':'passed','page_errors':errors}))
    browser.close()
