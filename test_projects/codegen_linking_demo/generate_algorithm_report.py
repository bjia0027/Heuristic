#!/usr/bin/env python3
"""
生成调度算法对比报告
"""
import json
from pathlib import Path

def main():
    benchmark_out = Path(__file__).parent / "benchmark_out"
    
    # 读取三种算法的统计数据
    random_stats = json.load(open(benchmark_out / "random_stats.json"))
    rr_stats = json.load(open(benchmark_out / "rr_stats.json"))
    heft_stats = json.load(open(benchmark_out / "heft_stats.json"))
    
    # 生成对比报告
    report = {
        "test_description": "200文件C++项目 - 三种调度算法真实分布式编译对比",
        "cluster_config": "10节点Docker集群 (4×8-slot + 4×4-slot + 2×2-slot)",
        "algorithms": {
            "Random": {
                "total_time": random_stats["total_compile_time"] + random_stats["total_link_time"],
                "compile_time": random_stats["total_compile_time"],
                "link_time": random_stats["total_link_time"],
                "phase_times": random_stats["phase_times"]
            },
            "RoundRobin": {
                "total_time": rr_stats["total_compile_time"] + rr_stats["total_link_time"],
                "compile_time": rr_stats["total_compile_time"],
                "link_time": rr_stats["total_link_time"],
                "phase_times": rr_stats["phase_times"]
            },
            "HEFT": {
                "total_time": heft_stats["total_compile_time"] + heft_stats["total_link_time"],
                "compile_time": heft_stats["total_compile_time"],
                "link_time": heft_stats["total_link_time"],
                "phase_times": heft_stats["phase_times"]
            }
        }
    }
    
    # 计算改进百分比
    random_time = report["algorithms"]["Random"]["total_time"]
    rr_time = report["algorithms"]["RoundRobin"]["total_time"]
    heft_time = report["algorithms"]["HEFT"]["total_time"]
    
    report["improvements"] = {
        "RR_vs_Random": f"{((random_time - rr_time) / random_time * 100):.2f}%",
        "HEFT_vs_Random": f"{((random_time - heft_time) / random_time * 100):.2f}%",
        "HEFT_vs_RR": f"{((rr_time - heft_time) / rr_time * 100):.2f}%"
    }
    
    # 保存JSON报告
    with open(benchmark_out / "algorithm_comparison.json", 'w') as f:
        json.dump(report, f, indent=2)
    
    # 打印可读报告
    print("="*70)
    print("调度算法对比报告 - 真实分布式编译")
    print("="*70)
    print(f"\n项目规模: 200个C++文件 (Foundation: 80, Middleware: 70, Application: 50)")
    print(f"集群配置: 10节点 (高性能4×8核 + 中等4×4核 + 低性能2×2核)")
    print(f"\n{'算法':<15} {'总时间(s)':<12} {'编译时间(s)':<15} {'链接时间(s)':<15}")
    print("-"*70)
    
    for algo, data in report["algorithms"].items():
        print(f"{algo:<15} {data['total_time']:<12.2f} {data['compile_time']:<15.2f} {data['link_time']:<15.2f}")
    
    print("\n" + "="*70)
    print("性能改进")
    print("="*70)
    print(f"RR vs Random:     {report['improvements']['RR_vs_Random']:>8}")
    print(f"HEFT vs Random:   {report['improvements']['HEFT_vs_Random']:>8}")
    print(f"HEFT vs RR:       {report['improvements']['HEFT_vs_RR']:>8}")
    
    print("\n" + "="*70)
    print("各阶段耗时对比 (秒)")
    print("="*70)
    phases = ["foundation", "middleware", "application"]
    print(f"{'阶段':<15} {'Random':<12} {'RR':<12} {'HEFT':<12}")
    print("-"*70)
    for phase in phases:
        r_time = report["algorithms"]["Random"]["phase_times"][phase]
        rr_time = report["algorithms"]["RoundRobin"]["phase_times"][phase]
        h_time = report["algorithms"]["HEFT"]["phase_times"][phase]
        print(f"{phase:<15} {r_time:<12.2f} {rr_time:<12.2f} {h_time:<12.2f}")
    
    print("\n报告已保存到: benchmark_out/algorithm_comparison.json")

if __name__ == "__main__":
    main()
