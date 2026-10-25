"""Beat-choreographed scenes: one module per scene, each exposing scene(T, t, B) -> (svg, background).

B is a motion.Beats with the start/end time of every narration line in the segment, so things
happen exactly when they're said. Register new modules in tools/scenes.py SCENES.
"""
