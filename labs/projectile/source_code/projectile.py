# Copyright (c) 2023, NVIDIA CORPORATION. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import physicsnemo
import physicsnemo.sym
import numpy as np
from sympy import Symbol

from physicsnemo.sym.hydra import instantiate_arch, PhysicsNeMoConfig
from physicsnemo.sym.solver import Solver
from physicsnemo.sym.domain import Domain
from physicsnemo.sym.geometry.primitives_1d import Point1D
from physicsnemo.sym.domain.constraint import PointwiseBoundaryConstraint
from physicsnemo.sym.domain.inferencer import PointwiseInferencer
from physicsnemo.sym.domain.validator import PointwiseValidator
from physicsnemo.sym.key import Key
from projectile_eqn import ProjectileEquation
from physicsnemo.sym.utils.io import ValidatorPlotter


@physicsnemo.sym.main(config_path="conf", config_name="config")
def run(cfg: PhysicsNeMoConfig) -> None:
    """Train the KSC projectile PINN and write validation artifacts."""

    gravity = float(cfg.custom.gravity)
    initial_speed = float(cfg.custom.initial_speed)
    launch_angle_deg = float(cfg.custom.launch_angle_deg)
    train_time_end = float(cfg.custom.train_time_end)
    inference_time_end = float(cfg.custom.inference_time_end)
    if gravity <= 0.0:
        raise ValueError("custom.gravity must be positive")
    if initial_speed <= 0.0:
        raise ValueError("custom.initial_speed must be positive")
    if not 0.0 < launch_angle_deg < 90.0:
        raise ValueError("custom.launch_angle_deg must be between 0 and 90")
    if train_time_end <= 0.0:
        raise ValueError("custom.train_time_end must be positive")
    if inference_time_end < train_time_end:
        raise ValueError(
            "custom.inference_time_end must be greater than or equal to "
            "custom.train_time_end"
        )

    launch_angle = np.deg2rad(launch_angle_deg)
    time = Symbol("t")

    # Equation node + neural-network node form one computational graph.
    pe = ProjectileEquation(gravity=gravity)
    projectile_net = instantiate_arch(
        input_keys=[Key("t")],
        output_keys=[Key("x"), Key("y")],
        cfg=cfg.arch.fully_connected,
    )
    nodes = pe.make_nodes() + [projectile_net.make_node(name="projectile_network")]

    # Point1D is a sampling anchor. Time is supplied through parameterization;
    # it is not a geometric representation of the projectile trajectory.
    geo = Point1D(0)
    projectile_domain = Domain()

    time_range = {time: (0.0, train_time_end)}
    velocity_x = initial_speed * np.cos(launch_angle)
    velocity_y = initial_speed * np.sin(launch_angle)

    print("=" * 72)
    print("KSC 발사체 PINN 실험값")
    print(f"초기속도: {initial_speed:.2f} m/s")
    print(f"발사각: {launch_angle_deg:.2f} deg")
    print(f"중력가속도 크기: {gravity:.4f} m/s^2")
    print(f"학습/검증 시간: 0 <= t < {train_time_end:.2f} s")
    print(f"추론 시간: 0 <= t < {inference_time_end:.2f} s")
    print("=" * 72)

    # Four initial conditions are required for two second-order ODEs.
    initial_condition = PointwiseBoundaryConstraint(
        nodes=nodes,
        geometry=geo,
        outvar={
            "x": 0.0,
            "y": 0.0,
            "x__t": velocity_x,
            "y__t": velocity_y,
        },
        batch_size=cfg.batch_size.initial_x,
        parameterization={time: 0.0},
    )
    projectile_domain.add_constraint(initial_condition, "initial_condition")

    # The equation class already expresses y'' + g = 0, so both residual
    # targets are zero. The constraint samples t through parameterization.
    ode_constraint = PointwiseBoundaryConstraint(
        nodes=nodes,
        geometry=geo,
        outvar={"ode_x": 0.0, "ode_y": 0.0},
        batch_size=cfg.batch_size.interior,
        parameterization=time_range,
    )
    projectile_domain.add_constraint(ode_constraint, "ode_constraint")


    # Setup validator
    time_validation = np.arange(0.0, train_time_end, 0.01)[:, None]
    x_validation = velocity_x * time_validation
    y_validation = (
        velocity_y * time_validation
        - 0.5 * gravity * time_validation**2
    )

    validator = PointwiseValidator(
        nodes=nodes,
        invar={"t": time_validation},
        true_outvar={"x": x_validation, "y": y_validation},
        batch_size=128,
        plotter=ValidatorPlotter(),
    )
    projectile_domain.add_validator(validator)

    # Times after train_time_end are extrapolation. This ODE omits collision
    # physics and continues the mathematical trajectory below y=0 after impact.
    time_inference = np.arange(0.0, inference_time_end, 0.001)[:, None]
    grid_inference = PointwiseInferencer(
        nodes=nodes,
        invar={"t": time_inference},
        output_names=["x", "y"],
        batch_size=128,
    )
    projectile_domain.add_inferencer(grid_inference, "inferencer_data")

    solver = Solver(cfg, projectile_domain)
    solver.solve()


if __name__ == "__main__":
    run()
