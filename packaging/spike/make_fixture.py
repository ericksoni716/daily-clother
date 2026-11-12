"""Regenerate the tiny fixtures committed under fixtures/.

Dev-only. Needs the `onnx` package, which is deliberately NOT in
requirements.txt (the build and the app never import it):

    pip install -r requirements.txt onnx==1.23.2
    python make_fixture.py

Outputs:
    fixtures/tiny_add.onnx  y = x + 1, float32 [1, 3, 4, 4] (about 100 bytes)
    fixtures/tiny.heic      16x16 HEIC, only used when HEIC encoding is unavailable
"""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def make_onnx(path: Path) -> None:
    import onnx
    from onnx import TensorProto, helper

    shape = [1, 3, 4, 4]
    graph = helper.make_graph(
        nodes=[helper.make_node("Add", ["x", "one"], ["y"])],
        name="tiny_add",
        inputs=[helper.make_tensor_value_info("x", TensorProto.FLOAT, shape)],
        outputs=[helper.make_tensor_value_info("y", TensorProto.FLOAT, shape)],
        initializer=[helper.make_tensor("one", TensorProto.FLOAT, [], [1.0])],
    )
    # Old opset / IR version on purpose: loadable by any recent onnxruntime.
    model = helper.make_model(
        graph,
        opset_imports=[helper.make_opsetid("", 13)],
        producer_name="closet-spike",
    )
    model.ir_version = 7
    onnx.checker.check_model(model)
    path.write_bytes(model.SerializeToString())


def make_heic(path: Path) -> None:
    import pillow_heif
    from PIL import Image

    pillow_heif.register_heif_opener()
    img = Image.new("RGB", (16, 16), (200, 60, 60))
    img.save(path, format="HEIF", quality=50)


def main() -> None:
    FIXTURES.mkdir(exist_ok=True)
    for name, fn in (("tiny_add.onnx", make_onnx), ("tiny.heic", make_heic)):
        target = FIXTURES / name
        fn(target)
        print(f"wrote {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
