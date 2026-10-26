# Description

Given a polyomino region R (the “lawn”), a polyomino C with some identified center c (the “cutter”), and a number k (the “swarm size”) of available cutters, this year's challenge problem asks for cutting the lawn with a swarm of k cutters as quickly as possible.

More formally, we need to find a feasible set of k closed rectilinear trajectories Ti,i=1,…,k: For each point t∈Ti on one of the trajectories, placing the center of C at t covers a subset τt(C) of points in R. For a set S={T1,...,Tk} of trajectories to be feasible, each point p∈R must be covered, that is, for each point p∈R, there must be a Ti in S and a t∈Ti such that p∈τt(C).

There are no extra constraints; in particular, the trajectories Ti are allowed to (fully) leave the region R and cutters are allowed to overlap or collide arbitrarily. There is no specified starting point, but each trajectory has to be closed, i.e., the cutter has to return to its starting point.

We further restrict the movement to turning points with integer coordinates. For one cutter, this is without loss of generality, as the movement is rectilinear and both R and T are polyominoes; for more than one cutter, this is a true restriction: the optimal solution with arbitrary rational turning points can be better than any solution that is restricted to integer turning points. We nonetheless impose that restriction to simplify the problem (and solution verification). However, for the challenge instances, we will try to use techniques such as scaling based on the number of cutters to avoid, at the very least, most cases where non-integer turning points could be helpful.

# Objective

Find a feasible set S of k trajectories, such that the longest trajectory is as short as possible