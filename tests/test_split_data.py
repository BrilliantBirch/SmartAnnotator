# -*- coding: utf-8 -*-
"""
数据集划分功能单元测试

作者: BaiBinnan
日期: 2026-08-10
"""
import os
import shutil
import tempfile
from pathlib import Path
import pytest
from smart_annotator.utils.tool import (
    split_data,
    _read_label_classes,
    _collect_class_ids,
    _count_instances,
    _stratified_split,
    _generate_split_report,
)


@pytest.fixture
def temp_dataset():
    """创建临时测试数据集"""
    temp_dir = tempfile.mkdtemp()
    dataset_dir = Path(temp_dir)
    
    # 创建目录结构
    images_dir = dataset_dir / "images"
    labels_dir = dataset_dir / "labels"
    images_dir.mkdir()
    labels_dir.mkdir()
    
    # 创建测试图片和标注文件
    # 类别0: 10张图片
    for i in range(10):
        img_path = images_dir / f"class0_img{i:03d}.jpg"
        img_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # 简化的JPEG头
        
        label_path = labels_dir / f"class0_img{i:03d}.txt"
        label_path.write_text(f"0 0.5 0.5 0.3 0.3\n")
    
    # 类别1: 5张图片
    for i in range(5):
        img_path = images_dir / f"class1_img{i:03d}.jpg"
        img_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        
        label_path = labels_dir / f"class1_img{i:03d}.txt"
        label_path.write_text(f"1 0.5 0.5 0.3 0.3\n")
    
    # 多类别图片: 3张（同时包含类别0和1）
    for i in range(3):
        img_path = images_dir / f"multi_img{i:03d}.jpg"
        img_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        
        label_path = labels_dir / f"multi_img{i:03d}.txt"
        label_path.write_text(f"0 0.3 0.3 0.2 0.2\n1 0.7 0.7 0.2 0.2\n")
    
    yield dataset_dir
    
    # 清理
    shutil.rmtree(temp_dir)


def test_read_label_classes(temp_dataset):
    """测试读取标签文件中的类别"""
    labels_dir = temp_dataset / "labels"
    
    # 测试单类别标签
    label_file = labels_dir / "class0_img000.txt"
    classes = _read_label_classes(label_file)
    assert classes == {0}, f"期望 {{0}}, 实际 {classes}"
    
    # 测试多类别标签
    label_file = labels_dir / "multi_img000.txt"
    classes = _read_label_classes(label_file)
    assert classes == {0, 1}, f"期望 {{0, 1}}, 实际 {classes}"


def test_collect_class_ids(temp_dataset):
    """测试收集所有类别ID"""
    images_dir = temp_dataset / "images"
    labels_dir = temp_dataset / "labels"
    
    samples = []
    for img_path in images_dir.iterdir():
        if img_path.suffix == ".jpg":
            label_path = labels_dir / f"{img_path.stem}.txt"
            if label_path.exists():
                samples.append((img_path, label_path))
    
    class_ids = _collect_class_ids(samples)
    assert class_ids == [0, 1], f"期望 [0, 1], 实际 {class_ids}"


def test_count_instances(temp_dataset):
    """测试实例统计"""
    images_dir = temp_dataset / "images"
    labels_dir = temp_dataset / "labels"
    
    samples = []
    for img_path in images_dir.iterdir():
        if img_path.suffix == ".jpg":
            label_path = labels_dir / f"{img_path.stem}.txt"
            if label_path.exists():
                samples.append((img_path, label_path))
    
    class_ids = [0, 1]
    inst_counter, img_counter, multi_label = _count_instances(samples, class_ids)
    
    # 类别0: 10张单类别 + 3张多类别 = 13个实例，13张图片
    assert inst_counter[0] == 13, f"类别0实例数期望13, 实际{inst_counter[0]}"
    assert img_counter[0] == 13, f"类别0图片数期望13, 实际{img_counter[0]}"
    
    # 类别1: 5张单类别 + 3张多类别 = 8个实例，8张图片
    assert inst_counter[1] == 8, f"类别1实例数期望8, 实际{inst_counter[1]}"
    assert img_counter[1] == 8, f"类别1图片数期望8, 实际{img_counter[1]}"
    
    # 多类别图片数
    assert multi_label == 3, f"多类别图片数期望3, 实际{multi_label}"


def test_stratified_split(temp_dataset):
    """测试分层抽样"""
    images_dir = temp_dataset / "images"
    labels_dir = temp_dataset / "labels"
    
    samples = []
    for img_path in images_dir.iterdir():
        if img_path.suffix == ".jpg":
            label_path = labels_dir / f"{img_path.stem}.txt"
            if label_path.exists():
                samples.append((img_path, label_path))
    
    ratio = (0.7, 0.2, 0.1)
    seed = 42
    
    train, val, test = _stratified_split(samples, ratio, seed)
    
    # 验证总数
    total = len(train) + len(val) + len(test)
    assert total == len(samples), f"总数不匹配: {total} != {len(samples)}"
    
    # 验证每个子集非空
    assert len(train) > 0, "训练集为空"
    assert len(val) > 0, "验证集为空"
    # test 可能为空（样本太少时）
    
    # 验证可重现性
    train2, val2, test2 = _stratified_split(samples, ratio, seed)
    assert len(train) == len(train2), "相同种子应产生相同结果"


def test_split_data_integration(temp_dataset):
    """测试完整的 split_data 函数"""
    messages = []

    def callback(msg, progress):
        messages.append((msg, progress))

    # 传入真实类别名称映射，验证报告中显示真实类别名而非 class_{id}
    class_names = {0: "cat", 1: "dog"}

    # 执行划分
    report = split_data(
        temp_dataset,
        split_ratios=(0.7, 0.2, 0.1),
        random_seed=42,
        class_names=class_names,
        callback=callback
    )
    
    # 验证返回值
    assert report is not None, "split_data 应返回报告字典"
    assert "total" in report, "报告应包含 total 字段"
    assert "train" in report, "报告应包含 train 字段"
    assert "val" in report, "报告应包含 val 字段"
    assert "test" in report, "报告应包含 test 字段"
    assert "class_stats" in report, "报告应包含 class_stats 字段"
    
    # 验证总数
    assert report["total"] == 18, f"总样本数期望18, 实际{report['total']}"
    
    # 验证目录结构
    assert (temp_dataset / "train" / "images").exists(), "train/images 目录不存在"
    assert (temp_dataset / "train" / "labels").exists(), "train/labels 目录不存在"
    assert (temp_dataset / "val" / "images").exists(), "val/images 目录不存在"
    assert (temp_dataset / "val" / "labels").exists(), "val/labels 目录不存在"
    assert (temp_dataset / "test" / "images").exists(), "test/images 目录不存在"
    assert (temp_dataset / "test" / "labels").exists(), "test/labels 目录不存在"
    
    # 验证源目录已删除
    assert not (temp_dataset / "images").exists(), "源 images 目录应已删除"
    assert not (temp_dataset / "labels").exists(), "源 labels 目录应已删除"

    # 验证报告文件已生成到输出目录
    report_path = temp_dataset / "split_report.txt"
    assert report_path.exists(), "报告文件 split_report.txt 应生成到输出目录"
    report_content = report_path.read_text(encoding="utf-8")
    assert "数据集划分统计报告" in report_content, "报告文件应包含标题"
    assert "总样本数" in report_content, "报告文件应包含总样本数"

    # 验证报告显示真实类别名（cat/dog）而非 class_{id}
    assert "cat" in report_content, "报告应显示真实类别名 cat"
    assert "dog" in report_content, "报告应显示真实类别名 dog"
    assert "class_0" not in report_content, "报告不应出现占位名 class_0"

    # 验证实例数统计正确（关键：修复前此处全为0）
    train_inst_total = report["class_stats"]["train"]["instances"]
    train_sum = sum(train_inst_total.values())
    assert train_sum > 0, f"训练集实例总数应大于0，实际: {train_sum}（修复前为0，因报告在文件移动后生成）"

    # 验证回调被调用
    assert len(messages) > 0, "回调函数应被调用"

    # 验证存在报告保存路径消息和完成消息
    msg_texts = [m[0] for m in messages]
    assert any("报告已保存至" in m for m in msg_texts), "应输出报告保存路径消息"
    assert any("完成" in m for m in msg_texts), f"应输出完成消息"


def test_split_data_error_handling():
    """测试错误处理"""
    # 测试不存在的目录
    report = split_data("/nonexistent/path", (0.7, 0.2, 0.1))
    assert report is None, "不存在的目录应返回 None"
    
    # 测试空目录
    temp_dir = tempfile.mkdtemp()
    try:
        dataset_dir = Path(temp_dir)
        (dataset_dir / "images").mkdir()
        (dataset_dir / "labels").mkdir()
        
        report = split_data(dataset_dir, (0.7, 0.2, 0.1))
        assert report is None, "空数据集应返回 None"
    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
