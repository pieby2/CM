from fpdf import FPDF

pdf = FPDF()
pdf.add_page()
pdf.set_font("Arial", size=12)

text = """Chapter 1: Quadratic Equations

A quadratic equation is any equation that can be rearranged in standard form as:
ax^2 + bx + c = 0 where x represents an unknown, and a, b, and c represent known numbers.

The term 'a' is the quadratic coefficient, 'b' is the linear coefficient, and 'c' is the constant.

The Discriminant:
The discriminant of the quadratic equation is given by: D = b^2 - 4ac

Properties of the Discriminant:
1. If D > 0, the equation has two distinct real roots.
2. If D = 0, the equation has exactly one real root (a repeated root).
3. If D < 0, the equation has no real roots; instead it has two complex roots.

Example 1:
Solve x^2 - 4x + 4 = 0.
Here, a=1, b=-4, c=4.
D = (-4)^2 - 4(1)(4) = 16 - 16 = 0.
Since D=0, there is exactly one real root.
"""

for line in text.split('\n'):
    pdf.multi_cell(0, 10, txt=line, align="L")

pdf.output("sample_math.pdf")
print("Successfully created sample_math.pdf using FPDF")
