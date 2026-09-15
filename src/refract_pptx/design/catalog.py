"""Operation arguments supplied to design agents; names share the compiler registry."""

OPERATION_ARGUMENTS = {
    "set_paragraph_alignment": {
        "paragraph_index": "zero-based",
        "alignment": "l, ctr, r or just; explicit source alignment required",
    },
    "set_paragraph_bullet": {
        "paragraph_index": "zero-based",
        "mode": "none or character; explicit source bullet required",
        "character": "single Unicode character if mode=character",
    },
    "set_paragraph_indent": {
        "paragraph_index": "zero-based",
        "margin_points": "0..200",
        "indent_points": "-200..200; both source fields must be explicit",
    },
    "remove_shape": {},
    "move_shape": {"dx_points": "number", "dy_points": "number"},
    "resize_shape": {"scale_x": "0.05..20", "scale_y": "0.05..20"},
    "swap_geometry": {"other_target": "selector for a distinct object on the same slide"},
    "change_z_order": {
        "index": "absolute shape-tree index, or use delta",
        "delta": "relative integer",
    },
    "set_text": {"text": "replacement text"},
    "set_fill": {"rgb": "six hexadecimal digits"},
    "remove_chart_title": {},
    "remove_chart_legend": {},
    "set_series_color": {"series_index": "zero-based integer", "rgb": "six hexadecimal digits"},
    "set_chart_value": {
        "series_index": "zero-based integer",
        "point_index": "zero-based integer",
        "value": "finite number; embedded workbook is updated too",
    },
    "set_table_cell_text": {"row": "zero-based", "column": "zero-based", "text": "replacement"},
    "set_table_cell_fill": {"row": "zero-based", "column": "zero-based", "rgb": "six hex digits"},
    "set_table_column_width": {"column": "zero-based", "width_points": "positive number"},
    "set_table_row_height": {"row": "zero-based", "height_points": "positive number"},
    "reverse_connector": {},
    "detach_connector_endpoint": {"endpoint": "start or end"},
    "set_connector_arrowhead": {"endpoint": "start or end", "arrow_type": "OOXML arrow preset"},
    "set_rotation": {"degrees": "-360..360; absolute rotation"},
    "set_flip": {
        "horizontal": "optional boolean",
        "vertical": "optional boolean; at least one required",
    },
    "set_picture_crop": {
        "left": "fraction 0..0.95",
        "top": "fraction 0..0.95",
        "right": "fraction 0..0.95",
        "bottom": "fraction 0..0.95; omitted sides become zero; opposing sums <0.98",
    },
    "set_shape_preset": {
        "preset": "rect, roundRect, ellipse, triangle, rtTriangle, diamond, parallelogram, "
        "trapezoid, hexagon, chevron, rightArrow or leftArrow"
    },
    "set_line_style": {
        "width_points": "optional 0..30",
        "rgb": "optional six hex digits",
        "dash": "optional preset dash; at least one field required; explicit RGB line required",
    },
    "set_font_size": {"points": "4..200; explicit source run/paragraph size required"},
    "set_text_color": {"rgb": "six hex digits; explicit source RGB required"},
    "set_text_emphasis": {
        "attribute": "bold, italic or underline; explicit source field required",
        "value": "boolean for bold/italic; none, sng or dbl for underline",
    },
    "set_chart_direction": {"value": "bar or col; single 2D bar plot only"},
    "set_chart_grouping": {
        "value": "clustered/stacked/percentStacked for bar; "
        "standard/stacked/percentStacked for line/area"
    },
    "set_chart_legend_position": {"value": "l, r, t, b or tr; existing legend required"},
    "set_chart_marker": {
        "series_index": "zero-based integer; line/scatter only",
        "value": "circle, dash, diamond, dot, none, plus, square, star, triangle or x",
    },
}
