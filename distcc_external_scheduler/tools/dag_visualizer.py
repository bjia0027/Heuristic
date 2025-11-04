"""
DAG可视化导出工具

支持将任务依赖图导出为DOT、PNG等格式，便于分析和调试
"""

import os
import subprocess
from typing import Optional, Dict, Any, List
from pathlib import Path
import networkx as nx
import logging

logger = logging.getLogger(__name__)


class DAGVisualizer:
    """DAG可视化导出器"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def export_to_dot(self, dag: nx.DiGraph, output_path: str, 
                      tasks: Optional[Dict[str, Any]] = None,
                      dag_info: Optional[Dict[str, Any]] = None) -> bool:
        """导出DAG为DOT格式
        
        Args:
            dag: NetworkX有向图
            output_path: 输出文件路径(.dot)
            tasks: 任务详情字典
            dag_info: DAG元信息
            
        Returns:
            是否成功导出
        """
        try:
            with open(output_path, 'w') as f:
                f.write('digraph DAG {\n')
                f.write('  rankdir=TB;\n')  # 从上到下布局
                f.write('  node [shape=box, style=filled];\n')
                
                # 图标题和信息
                if dag_info:
                    reason = dag_info.get('auto_dag_reason', 'unknown')
                    is_real = dag_info.get('is_real', False)
                    dag_type = "Real DAG" if is_real else "Heuristic DAG"
                    f.write(f'  labelloc="t";\n')
                    f.write(f'  label="{dag_type} ({reason})";\n\n')
                
                # 节点样式
                node_colors = {
                    'compile': 'lightblue',
                    'link': 'lightgreen', 
                    'gen': 'lightyellow'
                }
                
                # 添加节点
                for node_id in dag.nodes():
                    node_type = self._get_node_type(node_id)
                    color = node_colors.get(node_type, 'lightgray')
                    
                    # 节点标签
                    label = self._get_node_label(node_id, tasks)
                    
                    f.write(f'  "{node_id}" [fillcolor="{color}", label="{label}"];\n')
                
                f.write('\n')
                
                # 添加边
                for src, dst in dag.edges():
                    f.write(f'  "{src}" -> "{dst}";\n')
                
                # 图例
                f.write('\n  subgraph cluster_legend {\n')
                f.write('    label="Legend";\n')
                f.write('    style=filled;\n')
                f.write('    fillcolor=white;\n')
                f.write('    "compile_legend" [fillcolor="lightblue", label="Compile Task"];\n')
                f.write('    "gen_legend" [fillcolor="lightyellow", label="Generation Task"];\n')
                f.write('    "link_legend" [fillcolor="lightgreen", label="Link Task"];\n')
                f.write('  }\n')
                
                f.write('}\n')
            
            self.logger.info(f"DOT文件已导出: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"导出DOT失败: {e}")
            return False
    
    def export_to_png(self, dag: nx.DiGraph, output_path: str,
                      tasks: Optional[Dict[str, Any]] = None,
                      dag_info: Optional[Dict[str, Any]] = None) -> bool:
        """导出DAG为PNG图片
        
        Args:
            dag: NetworkX有向图
            output_path: 输出文件路径(.png)
            tasks: 任务详情字典
            dag_info: DAG元信息
            
        Returns:
            是否成功导出
        """
        try:
            # 先导出为DOT
            dot_path = output_path.replace('.png', '.dot')
            if not self.export_to_dot(dag, dot_path, tasks, dag_info):
                return False
            
            # 检查graphviz是否可用
            if not self._check_graphviz():
                self.logger.warning("未找到graphviz，无法生成PNG。请安装: sudo apt install graphviz")
                return False
            
            # 使用dot命令生成PNG
            result = subprocess.run([
                'dot', '-Tpng', dot_path, '-o', output_path
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.info(f"PNG图片已导出: {output_path}")
                # 清理临时DOT文件
                try:
                    os.unlink(dot_path)
                except:
                    pass
                return True
            else:
                self.logger.error(f"graphviz执行失败: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"导出PNG失败: {e}")
            return False
    
    def export_statistics(self, dag: nx.DiGraph, output_path: str,
                         tasks: Optional[Dict[str, Any]] = None,
                         dag_info: Optional[Dict[str, Any]] = None) -> bool:
        """导出DAG统计信息
        
        Args:
            dag: NetworkX有向图
            output_path: 输出文件路径(.txt)
            tasks: 任务详情字典
            dag_info: DAG元信息
            
        Returns:
            是否成功导出
        """
        try:
            with open(output_path, 'w') as f:
                f.write("DAG 统计信息报告\n")
                f.write("=" * 50 + "\n\n")
                
                # 基本信息
                if dag_info:
                    f.write("来源信息:\n")
                    f.write(f"  类型: {'真实DAG' if dag_info.get('is_real') else '启发式DAG'}\n")
                    f.write(f"  原因: {dag_info.get('auto_dag_reason', 'unknown')}\n")
                    f.write(f"  项目根目录: {dag_info.get('project_root', 'N/A')}\n\n")
                
                # 结构统计
                f.write("结构统计:\n")
                f.write(f"  节点数: {dag.number_of_nodes()}\n")
                f.write(f"  边数: {dag.number_of_edges()}\n")
                f.write(f"  密度: {nx.density(dag):.3f}\n\n")
                
                # 节点类型分布
                node_types = {}
                for node_id in dag.nodes():
                    node_type = self._get_node_type(node_id)
                    node_types[node_type] = node_types.get(node_type, 0) + 1
                
                f.write("节点类型分布:\n")
                for node_type, count in node_types.items():
                    f.write(f"  {node_type}: {count}\n")
                f.write("\n")
                
                # 拓扑特性
                if nx.is_directed_acyclic_graph(dag):
                    f.write("拓扑特性:\n")
                    f.write(f"  是否为DAG: 是\n")
                    
                    # 计算层次
                    try:
                        topo_levels = self._compute_topological_levels(dag)
                        f.write(f"  最大深度: {max(topo_levels.values()) if topo_levels else 0}\n")
                        
                        # 每层节点数
                        level_counts = {}
                        for node, level in topo_levels.items():
                            level_counts[level] = level_counts.get(level, 0) + 1
                        
                        f.write("  层次分布:\n")
                        for level in sorted(level_counts.keys()):
                            f.write(f"    Level {level}: {level_counts[level]} 节点\n")
                            
                    except Exception as e:
                        f.write(f"  层次分析失败: {e}\n")
                        
                else:
                    f.write("拓扑特性:\n")
                    f.write(f"  是否为DAG: 否 (存在循环)\n")
                
                f.write("\n")
                
                # 关键路径分析
                if dag.number_of_edges() > 0:
                    try:
                        critical_path = self._find_critical_path(dag, tasks)
                        f.write("关键路径分析:\n")
                        f.write(f"  关键路径长度: {len(critical_path)}\n")
                        if critical_path:
                            f.write("  关键路径节点:\n")
                            for i, node in enumerate(critical_path):
                                f.write(f"    {i+1}. {node}\n")
                        f.write("\n")
                    except Exception as e:
                        f.write(f"关键路径分析失败: {e}\n\n")
                
                # 度分布
                in_degrees = [dag.in_degree(node) for node in dag.nodes()]
                out_degrees = [dag.out_degree(node) for node in dag.nodes()]
                
                f.write("度分布:\n")
                f.write(f"  平均入度: {sum(in_degrees)/len(in_degrees):.2f}\n")
                f.write(f"  平均出度: {sum(out_degrees)/len(out_degrees):.2f}\n")
                f.write(f"  最大入度: {max(in_degrees) if in_degrees else 0}\n")
                f.write(f"  最大出度: {max(out_degrees) if out_degrees else 0}\n\n")
                
                # 根节点和叶节点
                root_nodes = [node for node in dag.nodes() if dag.in_degree(node) == 0]
                leaf_nodes = [node for node in dag.nodes() if dag.out_degree(node) == 0]
                
                f.write("特殊节点:\n")
                f.write(f"  根节点 ({len(root_nodes)}个):\n")
                for node in root_nodes[:10]:  # 最多显示10个
                    f.write(f"    - {node}\n")
                if len(root_nodes) > 10:
                    f.write(f"    ... 还有{len(root_nodes)-10}个\n")
                
                f.write(f"  叶节点 ({len(leaf_nodes)}个):\n")
                for node in leaf_nodes[:10]:
                    f.write(f"    - {node}\n")
                if len(leaf_nodes) > 10:
                    f.write(f"    ... 还有{len(leaf_nodes)-10}个\n")
            
            self.logger.info(f"统计信息已导出: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"导出统计信息失败: {e}")
            return False
    
    def _get_node_type(self, node_id: str) -> str:
        """根据节点ID判断节点类型"""
        if node_id.startswith('compile:'):
            return 'compile'
        elif node_id.startswith('link:'):
            return 'link'
        elif node_id.startswith('gen:'):
            return 'gen'
        else:
            return 'unknown'
    
    def _get_node_label(self, node_id: str, tasks: Optional[Dict[str, Any]] = None) -> str:
        """生成节点显示标签"""
        # 简化节点名称用于显示
        if node_id.startswith('compile:'):
            filename = node_id[8:]  # 去掉 'compile:' 前缀
            return os.path.basename(filename)
        elif node_id.startswith('gen:'):
            parts = node_id.split(':')
            if len(parts) >= 3:
                return f"{parts[1]}\\n{os.path.basename(parts[2])}"
            return node_id
        elif node_id.startswith('link:'):
            return node_id[5:]  # 去掉 'link:' 前缀
        else:
            return node_id
    
    def _check_graphviz(self) -> bool:
        """检查graphviz是否可用"""
        try:
            result = subprocess.run(['dot', '-V'], capture_output=True, text=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def _compute_topological_levels(self, dag: nx.DiGraph) -> Dict[str, int]:
        """计算节点的拓扑层级"""
        levels = {}
        
        # 使用拓扑排序计算层级
        for node in nx.topological_sort(dag):
            if dag.in_degree(node) == 0:
                levels[node] = 0
            else:
                max_pred_level = max(levels[pred] for pred in dag.predecessors(node))
                levels[node] = max_pred_level + 1
        
        return levels
    
    def _find_critical_path(self, dag: nx.DiGraph, 
                           tasks: Optional[Dict[str, Any]] = None) -> List[str]:
        """查找关键路径（最长路径）"""
        if not nx.is_directed_acyclic_graph(dag):
            return []
        
        # 简化版：找到从根到叶的最长路径
        root_nodes = [node for node in dag.nodes() if dag.in_degree(node) == 0]
        leaf_nodes = [node for node in dag.nodes() if dag.out_degree(node) == 0]
        
        if not root_nodes or not leaf_nodes:
            return []
        
        longest_path = []
        max_length = 0
        
        # 尝试所有根到叶的路径
        for root in root_nodes:
            for leaf in leaf_nodes:
                try:
                    if nx.has_path(dag, root, leaf):
                        path = nx.shortest_path(dag, root, leaf)
                        if len(path) > max_length:
                            max_length = len(path)
                            longest_path = path
                except nx.NetworkXNoPath:
                    continue
        
        return longest_path


# 便捷函数
def export_dag_visualization(dag: nx.DiGraph, output_dir: str, 
                           basename: str = "dag",
                           tasks: Optional[Dict[str, Any]] = None,
                           dag_info: Optional[Dict[str, Any]] = None,
                           formats: List[str] = ['dot', 'png', 'stats']) -> Dict[str, bool]:
    """一键导出DAG的多种可视化格式
    
    Args:
        dag: NetworkX有向图
        output_dir: 输出目录
        basename: 文件基础名
        tasks: 任务详情字典
        dag_info: DAG元信息
        formats: 导出格式列表 ['dot', 'png', 'stats']
        
    Returns:
        各格式的导出成功状态字典
    """
    os.makedirs(output_dir, exist_ok=True)
    visualizer = DAGVisualizer()
    results = {}
    
    for fmt in formats:
        if fmt == 'dot':
            output_path = os.path.join(output_dir, f"{basename}.dot")
            results[fmt] = visualizer.export_to_dot(dag, output_path, tasks, dag_info)
        elif fmt == 'png':
            output_path = os.path.join(output_dir, f"{basename}.png") 
            results[fmt] = visualizer.export_to_png(dag, output_path, tasks, dag_info)
        elif fmt == 'stats':
            output_path = os.path.join(output_dir, f"{basename}_stats.txt")
            results[fmt] = visualizer.export_statistics(dag, output_path, tasks, dag_info)
    
    return results


if __name__ == "__main__":
    # 测试可视化功能
    import sys
    sys.path.insert(0, '..')
    from core.dag_heuristic_scheduler import DAGHeuristicScheduler
    from core.types import CompileTask, ServerNode, NodeStatus
    
    # 创建测试DAG
    scheduler = DAGHeuristicScheduler()
    tasks = [
        CompileTask(task_id="compile:main.cpp", source_file="main.cpp"),
        CompileTask(task_id="compile:src/utils.cpp", source_file="src/utils.cpp"),
        CompileTask(task_id="compile:src/lib/core.cpp", source_file="src/lib/core.cpp")
    ]
    
    nodes = [ServerNode(node_id='node1', hostname='localhost', max_slots=4, status=NodeStatus.ONLINE)]
    
    # 触发DAG生成
    for task in tasks:
        scheduler.select_node(task, nodes, all_tasks=tasks)
    
    if scheduler._inferred_dag:
        dag_info = scheduler.get_dag_source_info()
        
        # 导出可视化
        results = export_dag_visualization(
            scheduler._inferred_dag,
            output_dir="/tmp",
            basename="test_dag", 
            dag_info=dag_info,
            formats=['dot', 'png', 'stats']
        )
        
        print("可视化导出结果:")
        for fmt, success in results.items():
            status = "成功" if success else "失败"
            print(f"  {fmt}: {status}")
    else:
        print("未生成DAG")