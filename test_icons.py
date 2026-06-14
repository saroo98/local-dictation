import unittest

import icons


class HexTests(unittest.TestCase):
    def test_hex_to_rgb(self):
        self.assertEqual(icons.hex_to_rgb("#1f6f4a"), (31, 111, 74))
        self.assertEqual(icons.hex_to_rgb("ffffff"), (255, 255, 255))

    def test_hex_to_rgb_bad_input_is_white(self):
        self.assertEqual(icons.hex_to_rgb("#xyz"), (255, 255, 255))


@unittest.skipUnless(icons.PIL_AVAILABLE, "Pillow required")
class RenderTests(unittest.TestCase):
    def test_bubble_is_rgba_window_sized(self):
        img = icons.render_bubble_rgba("check", "#188038", "#3a9659", 38, 32)
        self.assertEqual(img.size, (38, 38))
        self.assertEqual(img.mode, "RGBA")

    def test_bubble_corners_are_transparent(self):
        img = icons.render_bubble_rgba("play", "#1f6f4a", "#3a8466", 38, 32)
        self.assertEqual(img.getpixel((0, 0))[3], 0)
        self.assertEqual(img.getpixel((37, 37))[3], 0)

    def test_bubble_all_glyphs_render(self):
        for glyph in ["play", "stop", "ellipsis", "paste", "check", "error", "text"]:
            img = icons.render_bubble_rgba(glyph, "#1f6f4a", "#3a8466", 38, 32, text="-")
            self.assertEqual(img.size, (38, 38))

    def test_glyph_icons_are_rgba(self):
        for name in ["history", "settings", "close", "export", "save"]:
            img = icons.render_glyph(name, "#f2f2f2", 22)
            self.assertEqual(img.size, (22, 22))
            self.assertEqual(img.mode, "RGBA")


if __name__ == "__main__":
    unittest.main()
