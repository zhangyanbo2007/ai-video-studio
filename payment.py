"""
支付模块 — 兑换码模式

管理员命令：
  python payment.py generate --credits 10 --count 10
  python payment.py list
"""

REDEEM_PLANS = {
    "single": {
        "name": "单次体验",
        "credits": 1,
        "type": "per_use",
        "desc": "1 次视频生成",
        "price_hint": "免费体验",
    },
    "pack_10": {
        "name": "10次包",
        "credits": 10,
        "type": "per_use",
        "desc": "10 次视频生成",
        "price_hint": "¥30",
    },
    "pack_30": {
        "name": "30次包",
        "credits": 30,
        "type": "per_use",
        "desc": "30 次视频生成",
        "price_hint": "¥80",
    },
    "standard": {
        "name": "月卡·标准",
        "credits": 60,
        "type": "subscription",
        "days": 30,
        "desc": "60 次/月",
        "price_hint": "¥149.9",
    },
    "pro": {
        "name": "月卡·专业",
        "credits": 200,
        "type": "subscription",
        "days": 30,
        "desc": "200 次/月",
        "price_hint": "¥299.9",
    },
}


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="兑换码管理")
    sub = parser.add_subparsers(dest="cmd")

    gen = sub.add_parser("generate", help="生成兑换码")
    gen.add_argument("--credits", type=int, required=True, help="积分数量")
    gen.add_argument("--count", type=int, default=1, help="生成数量")
    gen.add_argument("--plan", type=str, default=None, help="套餐名")

    sub.add_parser("list", help="查看未使用的兑换码")

    args = parser.parse_args()

    from pathlib import Path
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                import os
                os.environ.setdefault(key.strip(), value.strip())

    import database as db
    db.init_db()

    if args.cmd == "generate":
        codes = db.generate_redeem_codes(args.credits, args.count, args.plan)
        print(f"生成 {len(codes)} 个兑换码（{args.credits} 次）:")
        for c in codes:
            print(f"  {c}")
    elif args.cmd == "list":
        codes = db.list_redeem_codes()
        if not codes:
            print("没有未使用的兑换码")
        else:
            print(f"未使用兑换码 ({len(codes)} 个):")
            for c in codes:
                print(f"  {c['code']}  |  {c['credits']}次  |  {c['created_at']}")
    else:
        parser.print_help()
