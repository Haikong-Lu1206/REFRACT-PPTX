from __future__ import annotations

import base64
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"


def _shape(shape_id: int, name: str, text: str, x: int, y: int, cx: int, cy: int) -> str:
    return f"""
    <p:sp>
      <p:nvSpPr><p:cNvPr id="{shape_id}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr>
        <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        <a:solidFill><a:srgbClr val="4472C4"/></a:solidFill>
      </p:spPr>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody>
    </p:sp>
    """


@pytest.fixture
def workspace_tmp() -> Path:
    path = Path(".test_tmp") / uuid4().hex
    path.mkdir(parents=True)
    return path


@pytest.fixture
def synthetic_pptx(workspace_tmp: Path) -> Path:
    path = workspace_tmp / "synthetic.pptx"
    presentation = f"""
    <p:presentation xmlns:p="{P}" xmlns:r="{R}">
      <p:sldIdLst>
        <p:sldId id="256" r:id="rId1"/>
        <p:sldId id="257" r:id="rId2"/>
      </p:sldIdLst>
      <p:sldSz cx="12192000" cy="6858000"/>
    </p:presentation>
    """
    presentation_rels = f"""
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="{R}/slide" Target="slides/slide1.xml"/>
      <Relationship Id="rId2" Type="{R}/slide" Target="slides/slide2.xml"/>
    </Relationships>
    """
    slide1 = f"""
    <p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}" xmlns:c="{C}">
      <p:cSld><p:spTree>
        <p:nvGrpSpPr/><p:grpSpPr/>
        {_shape(2, "Title", "Quarterly project overview", 635000, 381000, 4445000, 762000)}
        {_shape(3, "Status", "On track", 635000, 1524000, 4445000, 762000)}
        <p:pic>
          <p:nvPicPr><p:cNvPr id="4" name="Project image"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
          <p:blipFill><a:blip r:embed="rId3"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
          <p:spPr>
            <a:xfrm><a:off x="6350000" y="635000"/>
              <a:ext cx="3810000" cy="2540000"/></a:xfrm>
            <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          </p:spPr>
        </p:pic>
        <p:graphicFrame>
          <p:nvGraphicFramePr><p:cNvPr id="5" name="Summary table"/>
            <p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>
          <p:xfrm><a:off x="635000" y="3048000"/><a:ext cx="4445000" cy="1905000"/></p:xfrm>
          <a:graphic><a:graphicData uri="{A}/table"><a:tbl/></a:graphicData></a:graphic>
        </p:graphicFrame>
        <p:graphicFrame>
          <p:nvGraphicFramePr><p:cNvPr id="6" name="Revenue chart"/>
            <p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>
          <p:xfrm><a:off x="5715000" y="3429000"/><a:ext cx="5080000" cy="2540000"/></p:xfrm>
          <a:graphic><a:graphicData uri="{C}"><c:chart r:id="rId1"/></a:graphicData></a:graphic>
        </p:graphicFrame>
        <p:graphicFrame>
          <p:nvGraphicFramePr><p:cNvPr id="7" name="Process diagram"/>
            <p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>
          <p:xfrm><a:off x="381000" y="5715000"/><a:ext cx="2540000" cy="635000"/></p:xfrm>
          <a:graphic><a:graphicData uri="{A}/diagram">
            <a:relIds r:dm="rId2"/></a:graphicData></a:graphic>
        </p:graphicFrame>
      </p:spTree></p:cSld>
      <p:transition/>
    </p:sld>
    """
    slide2 = f"""
      <p:sld xmlns:p="{P}" xmlns:a="{A}">
      <p:cSld><p:spTree>
        <p:nvGrpSpPr/><p:grpSpPr/>
        {_shape(2, "Closing", "Next steps", 1270000, 1270000, 3810000, 762000)}
        <p:grpSp>
          <p:nvGrpSpPr><p:cNvPr id="3" name="Milestone group"/>
            <p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
          <p:grpSpPr><a:xfrm><a:off x="1270000" y="2540000"/>
            <a:ext cx="3810000" cy="1905000"/><a:chOff x="0" y="0"/>
            <a:chExt cx="3810000" cy="1905000"/></a:xfrm></p:grpSpPr>
        </p:grpSp>
        <p:cxnSp>
          <p:nvCxnSpPr><p:cNvPr id="4" name="Flow connector"/>
            <p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr>
          <p:spPr><a:xfrm><a:off x="5715000" y="2540000"/>
            <a:ext cx="1905000" cy="0"/></a:xfrm>
            <a:prstGeom prst="line"><a:avLst/></a:prstGeom></p:spPr>
        </p:cxnSp>
      </p:spTree></p:cSld>
      <p:timing/>
    </p:sld>
    """
    rels = f"""
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1"
        Type="{R}/chart"
        Target="../charts/chart1.xml"/>
      <Relationship Id="rId2"
        Type="{R}/diagramData"
        Target="../diagrams/data1.xml"/>
      <Relationship Id="rId3" Type="{R}/image" Target="../media/image1.png"/>
    </Relationships>
    """
    chart = f"""
    <c:chartSpace xmlns:c="{C}" xmlns:a="{A}">
      <c:chart><c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>Revenue</a:t></a:r></a:p></c:rich></c:tx></c:title>
        <c:plotArea><c:layout/><c:barChart><c:barDir val="col"/><c:ser>
          <c:idx val="0"/><c:order val="0"/><c:tx><c:v>Actual</c:v></c:tx>
          <c:spPr><a:solidFill><a:srgbClr val="70AD47"/></a:solidFill></c:spPr>
          <c:val><c:numLit><c:ptCount val="3"/>
            <c:pt idx="0"><c:v>12</c:v></c:pt>
            <c:pt idx="1"><c:v>18</c:v></c:pt>
            <c:pt idx="2"><c:v>27</c:v></c:pt>
          </c:numLit></c:val>
        </c:ser></c:barChart></c:plotArea><c:legend/></c:chart>
    </c:chartSpace>
    """
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("ppt/presentation.xml", presentation)
        package.writestr("ppt/_rels/presentation.xml.rels", presentation_rels)
        package.writestr("ppt/slides/slide1.xml", slide1)
        package.writestr("ppt/slides/slide2.xml", slide2)
        package.writestr("ppt/slides/_rels/slide1.xml.rels", rels)
        package.writestr("ppt/charts/chart1.xml", chart)
        package.writestr("ppt/diagrams/data1.xml", "<data/>")
        package.writestr(
            "ppt/media/image1.png",
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
                "AScY42YAAAAASUVORK5CYII="
            ),
        )
        package.writestr("ppt/notesSlides/notesSlide1.xml", "<notes/>")
        package.writestr("ppt/slideMasters/slideMaster1.xml", "<master/>")
        package.writestr("ppt/slideLayouts/slideLayout1.xml", "<layout/>")
    return path
