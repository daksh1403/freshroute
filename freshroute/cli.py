import argparse
import json
import logging
from freshroute.model import ValidationError
from freshroute.io import load_scenario, save_report
from freshroute.engine import baseline, optimize
from freshroute.evaluation import evaluate
from freshroute.benchmark import run_benchmark


def main():
    parser = argparse.ArgumentParser(description='FreshRoute: validated perishable produce allocation')
    parser.add_argument('--verbose',action='store_true')
    sub = parser.add_subparsers(dest='command',required=True)
    solve = sub.add_parser('solve'); solve.add_argument('input'); solve.add_argument('--output',default='reports/plan')
    solve.add_argument('--column-map',help='JSON mapping: table -> source column -> canonical column')
    solve.add_argument('--time-limit',type=float,default=15)
    bench = sub.add_parser('benchmark'); bench.add_argument('inputs',nargs='*'); bench.add_argument('--output',default='reports/benchmark')
    bench.add_argument('--time-limit',type=float,default=15)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,format='%(levelname)s %(name)s: %(message)s')
    try:
        if args.command == 'solve':
            with open(args.column_map) if args.column_map else open(__file__) as f:
                mapping = json.load(f) if args.column_map else None
            s = load_scenario(args.input,column_map=mapping)
            b,p = baseline(s),optimize(s,args.time_limit)
            save_report(s,b,p,args.output)
            metrics = evaluate(s,p)
            print(json.dumps({'status':p.status,'baseline_net_revenue':evaluate(s,b)['net_revenue'],
                              'optimized_metrics':metrics,'reports':args.output},indent=2))
            return 2 if metrics['constraint_violations'] else 0
        summary = run_benchmark(args.output,args.inputs,args.time_limit)
        print(json.dumps({k:v for k,v in summary.items() if k != 'cases'},indent=2))
        return 2 if summary['constraint_violations'] or summary['revenue_regressions'] else 0
    except (ValidationError,OSError,ValueError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())
