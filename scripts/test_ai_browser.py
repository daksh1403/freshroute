"""Real Gemma + real Python solver acceptance. No mocked inference."""
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright,expect

base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8787'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    try:
        page.goto(base,wait_until='domcontentloaded')
        expect(page.locator('#generate')).to_be_enabled(timeout=300000)
        page.locator('[data-tab="ai-import"]').click()
        page.locator('#ai-image').set_input_files('examples/ai/printed_inventory.png')
        page.locator('#ai-consent').check()
        page.locator('#ai-extract').click()
        expect(page.locator('#ai-review')).to_be_visible(timeout=90000)
        draft=json.loads(page.locator('#ai-draft').input_value())
        assert len(draft['inventory'])==3,draft
        assert sorted(row['quantity'] for row in draft['inventory'])==[45,90,120]
        page.screenshot(path='/tmp/freshroute-live-ai-review.png',full_page=True)
        page.locator('#ai-apply').click()
        expect(page.locator('#ai-progress')).to_contain_text('Human verification')
        assert page.evaluate('window.FreshRoute.getScenario().inventory.reduce((a,b)=>a+Number(b.quantity),0)')==740
        draft['inventory'][0]['batch_id']='REVIEWED-PRINTED-1'
        page.locator('#ai-draft').fill(json.dumps(draft,indent=2))
        page.locator('#ai-import-mode').select_option('replace')
        page.locator('#ai-confirm').check()
        page.locator('#ai-apply').click()
        expect(page.locator('#violations')).to_have_text('0',timeout=60000)
        expect(page.locator('#overview')).to_have_class('tab-panel active')
        report=page.evaluate('window.FreshRoute.getResult()')
        assert abs(report['optimized_metrics']['inventory_quantity']-255)<1e-6
        assert report['optimized_metrics']['constraint_violations']==[]
        page.locator('[data-tab="ai-import"]').click()
        with page.expect_download() as d:page.locator('#ai-audit-download').click()
        audit=json.loads(Path(d.value.path()).read_text())
        assert audit['confirmed'] and audit['manual_corrections']
        assert audit['model']=='gemma-4-26b-a4b-it'
        assert len(audit['source']['image']['sha256'])==64
        page.locator('[data-tab="ai-whatif"]').click()
        page.locator('#ai-whatif-question').fill('What if route R-CHG is delayed by three hours?')
        page.locator('#ai-whatif-propose').click()
        expect(page.locator('#ai-whatif-proposal')).to_be_visible(timeout=90000)
        operations=json.loads(page.locator('#ai-operations').input_value())
        assert operations==[{'op':'delay_route','route_id':'R-CHG','hours':3}],operations
        page.locator('#ai-whatif-confirm').check()
        page.locator('#ai-whatif-run').click()
        expect(page.locator('#ai-whatif-results')).to_contain_text('Actual recalculated results',timeout=60000)
        page.locator('#ai-explain-updated').click()
        expect(page.locator('#ai-updated-explanation')).to_contain_text('GEMMA-GENERATED',timeout=90000)
        with page.expect_download() as d:page.locator('#ai-download-updated').click()
        updated=json.loads(Path(d.value.path()).read_text())
        assert updated['optimized_metrics']['constraint_violations']==[]
        assert updated['replanning']['changes']
        page.screenshot(path='/tmp/freshroute-live-ai-whatif.png',full_page=True)
        assert not errors,errors
        summary={'base':base,'model':audit['model'],'live_image_extraction':True,'human_confirmation_checked':True,'manual_edit_audited':True,'extracted_inventory_quantity':255,'baseline_net':report['baseline_metrics']['net_revenue'],'optimized_net':report['optimized_metrics']['net_revenue'],'updated_net':updated['optimized_metrics']['net_revenue'],'grounded_explanation':True,'constraint_violations':0,'page_errors':errors}
        Path('reports/ai').mkdir(parents=True,exist_ok=True)
        Path('reports/ai/browser-acceptance.json').write_text(json.dumps(summary,indent=2))
        print(json.dumps(summary))
    except Exception:
        for name in ['error','runtime-status','ai-progress','ai-whatif-progress','ai-updated-explanation']:
            if page.locator('#'+name).count():print(name,page.locator('#'+name).inner_text()[:2500])
        raise
    finally:browser.close()
