from __future__ import annotations

import zipfile
from pathlib import Path
from uuid import uuid4

import pytest

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


@pytest.fixture
def workspace_tmp() -> Path:
    path = Path(".test_tmp") / uuid4().hex
    path.mkdir(parents=True)
    return path


@pytest.fixture
def synthetic_pptx(workspace_tmp: Path) -> Path:
    path = workspace_tmp / "synthetic.pptx"
    presentation = f"""
    <p:presentation xmlns:p="{P}">
      <p:sldSz cx="12192000" cy="6858000"/>
    </p:presentation>
    """
    slide1 = f"""
    <p:sld xmlns:p="{P}" xmlns:a="{A}">
      <p:cSld><p:spTree>
        <p:nvGrpSpPr/><p:grpSpPr/>
        <p:sp><p:txBody><a:p><a:r>
          <a:t>Quarterly project overview</a:t>
        </a:r></a:p></p:txBody></p:sp>
        <p:pic/>
        <p:graphicFrame><a:graphic><a:graphicData><a:tbl/></a:graphicData></a:graphic></p:graphicFrame>
      </p:spTree></p:cSld>
      <p:transition/>
    </p:sld>
    """
    slide2 = f"""
    <p:sld xmlns:p="{P}" xmlns:a="{A}">
      <p:cSld><p:spTree>
        <p:nvGrpSpPr/><p:grpSpPr/>
        <p:grpSp><p:sp/></p:grpSp>
        <p:cxnSp/>
        <p:graphicFrame/>
      </p:spTree></p:cSld>
      <p:timing/>
    </p:sld>
    """
    rels = """
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1"
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart"
        Target="../charts/chart1.xml"/>
      <Relationship Id="rId2"
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/diagramData"
        Target="../diagrams/data1.xml"/>
    </Relationships>
    """
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("ppt/presentation.xml", presentation)
        package.writestr("ppt/slides/slide1.xml", slide1)
        package.writestr("ppt/slides/slide2.xml", slide2)
        package.writestr("ppt/slides/_rels/slide1.xml.rels", rels)
        package.writestr("ppt/media/image1.png", b"synthetic")
        package.writestr("ppt/notesSlides/notesSlide1.xml", "<notes/>")
        package.writestr("ppt/slideMasters/slideMaster1.xml", "<master/>")
        package.writestr("ppt/slideLayouts/slideLayout1.xml", "<layout/>")
    return path
