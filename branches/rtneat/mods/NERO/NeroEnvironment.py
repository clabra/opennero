import copy
import math
import random
import sys
import time

import common
import OpenNero
import module
import constants

class AgentState:
    """
    State that we keep for each agent
    """
    def __init__(self, agent):
        self.id = agent.state.id
        # current x, y, heading pose
        self.pose = (0, 0, 0)
        # previous x, y, heading pose
        self.prev_pose = (0, 0, 0)
        # starting position
        self.initial_position = OpenNero.Vector3f(0, 0, 0)
        # starting orientation
        self.initial_rotation = OpenNero.Vector3f(0, 0, 0)
        self.total_damage = 0
        self.curr_damage = 0
    def __str__(self):
        x, y, h = self.pose
        px, py, ph = self.prev_pose
        return 'agent { id: %d, pose: (%.02f, %.02f, %.02f), prev_pose: (%.02f, %.02f, %.02f) }' % \
            (self.id, x, y, h, px, py, ph)

class NeroEnvironment(OpenNero.Environment):
    """
    Environment for the Nero
    """
    def __init__(self):
        """
        Create the environment
        """
        OpenNero.Environment.__init__(self)

        self.curr_id = 0
        self.max_steps = 20
        self.MAX_DIST = math.hypot(constants.XDIM, constants.YDIM)
        self.states = {}
        self.teams = {}

        abound = OpenNero.FeatureVectorInfo() # actions
        sbound = OpenNero.FeatureVectorInfo() # sensors
        rbound = OpenNero.FeatureVectorInfo() # rewards

        # actions
        abound.add_continuous(-1, 1) # forward/backward speed
        abound.add_continuous(-0.2, 0.2) # left/right turn (in radians)

        # sensor dimensions
        for a in range(constants.N_SENSORS):
            sbound.add_continuous(0, 1);

        # Rewards
        # the enviroment returns the raw multiple dimensions of the fitness as
        # they get each step. This then gets combined into, e.g. Z-score, by
        # the ScoreHelper in order to calculate the final rtNEAT-fitness
        for f in constants.FITNESS_DIMENSIONS:
            # we don't care about the bounds of the individual dimensions
            rbound.add_continuous(-sys.float_info.max, sys.float_info.max) # range for reward

        # initialize the rtNEAT algorithm parameters
        # input layer has enough nodes for all the observations plus a bias
        # output layer has enough values for all the actions
        # population size matches ours
        # 1.0 is the weight initialization noise
        rtneat = OpenNero.RTNEAT("data/ai/neat-params.dat",
                                 constants.N_SENSORS,
                                 constants.N_ACTIONS,
                                 constants.pop_size,
                                 1.0,
                                 rbound)

        OpenNero.set_ai("rtneat", rtneat)
        print "get_ai(rtneat):", OpenNero.get_ai("rtneat")

        # set the initial lifetime
        lifetime = module.getMod().lt
        rtneat.set_lifetime(lifetime)
        print 'rtNEAT lifetime:', lifetime

        self.agent_info = OpenNero.AgentInitInfo(sbound, abound, rbound)

    def reset(self, agent):
        """
        reset the environment to its initial state
        """
        state = self.get_state(agent)
        if agent.group == "Agent":
            dx = random.randrange(constants.XDIM / 20) - constants.XDIM / 40
            dy = random.randrange(constants.XDIM / 20) - constants.XDIM / 40
            # TODO: initialization code should be inside AgentState
            state.initial_position.x = module.getMod().spawn_x + dx
            state.initial_position.y = module.getMod().spawn_y + dy
            agent.state.position = copy.copy(state.initial_position)
            agent.state.rotation = copy.copy(state.initial_rotation)
            state.pose = (state.initial_position.x, state.initial_position.y, state.initial_rotation.z)
            state.prev_pose = state.pose
            agent.state.update_immediately()
        state.total_damage = 0
        state.curr_damage = 0
        self.getFriendFoe(agent)
        return True

    def get_agent_info(self, agent):
        """
        return a blueprint for a new agent
        """
        for a in constants.WALL_RAY_SENSORS:
            agent.add_sensor(OpenNero.RaySensor(math.cos(math.radians(a)), math.sin(math.radians(a)), 0, 50, constants.OBJECT_TYPE_OBSTACLE, False))
        for a0, a1 in constants.FLAG_RADAR_SENSORS:
            agent.add_sensor(OpenNero.RadarSensor(a0, a1, -90, 90, constants.MAX_VISION_RADIUS, constants.OBJECT_TYPE_FLAG, False))
        for a0, a1 in constants.ENEMY_RADAR_SENSORS:
            if agent.get_team() == 0: agent.add_sensor(OpenNero.RadarSensor(a0, a1, -90, 90, constants.MAX_VISION_RADIUS, constants.OBJECT_TYPE_TEAM_1, False))
            if agent.get_team() == 1: agent.add_sensor(OpenNero.RadarSensor(a0, a1, -90, 90, constants.MAX_VISION_RADIUS, constants.OBJECT_TYPE_TEAM_0, False))
        return self.agent_info

    def get_state(self, agent):
        """
        Returns the state of an agent
        """
        if agent in self.states:
            return self.states[agent]
        else:
            self.states[agent] = AgentState(agent)
            if agent.get_team() not in  self.teams:
                self.teams[agent.get_team()] = {}
            self.teams[agent.get_team()][agent] = self.states[agent]
            return self.states[agent]

    def getStateId(self, id):
        """
        Searches for the state with the given ID
        """
        for state in self.states:
            if id == self.states[state].id:
                return self.states[state]
        else:
            return - 1

    def getFriendFoe(self, agent):
        """
        Returns lists of all friend agents and all foe agents.
        """
        friend = []
        foe = []
        if agent.get_team() in self.teams:
            friend = self.teams[agent.get_team()]
        if 1-agent.get_team() in self.teams:
            foe = self.teams[1-agent.get_team()]
        else:
            foe = []
        return friend, foe

    def target(self, agent):
        #Get list of all targets
        friends, foes = self.getFriendFoe(agent)
        if not friends:
            return None

        state = self.get_state(agent)
        x, y, r = state.pose

        #sort in order of variance from 0~2 degrees (maybe more)
        valids = []
        for f in foes:
            p = foes[f].pose
            fd = self.distance(state.pose, p)
            fh = 0
            if fd != 0:
                fh = abs((math.degrees(math.atan2(p[1] - y, p[0] - x)) - r) % 360)
            if fh <= 2:
                valids.append((f, fd, fh))

        #Valids contains (state, distance, heading to distance) pairs
        #get one that is nearest based on distance / cos(radians(degrees() * 20))
        min_a = None
        min_v = None
        for a, fd, fh in valids:
            v = fd / math.cos(math.radians(fh * 20))
            if min_v is None or v < min_v:
                min_a = a
                min_v = v
        return min_a

    def step(self, agent, action):
        """
        2A step for an agent
        """
        # check if the action is valid
        assert(self.agent_info.actions.validate(action))

        state = self.get_state(agent)

        # get the reward (which has multiple components)
        reward = self.agent_info.reward.get_instance()

        #Initilize Agent state
        if agent.step == 0 and agent.group != "Turret":
            p = copy.copy(agent.state.position)
            r = copy.copy(agent.state.rotation)
            if agent.group == "Agent":
                r.z = random.randrange(360)
                agent.state.rotation = r
            # TODO: move into a member function of state
            state.initial_position = p
            state.initial_rotation = r
            state.pose = (p.x, p.y, r.z)
            state.prev_pose = (p.x, p.y, r.z)
            return reward

        # Spawn more agents if there are more to spawn
        if OpenNero.get_ai("rtneat").ready():
            if module.getMod().getNumToAdd() > 0:
                module.getMod().addAgent()

        # Update Damage totals
        # TODO: move into a member function of state
        state.total_damage += state.curr_damage
        damage = state.curr_damage
        state.curr_damage = 0

        #Fitness Function Parameters
        # TODO: make these less opaque
        distance_st = module.getMod().dta
        distance_ae = module.getMod().dtb
        distance_af = module.getMod().dtc
        friendly_fire = module.getMod().ff

        # the position and the rotation of the agent on-screen
        position = copy.copy(agent.state.position)
        rotation = copy.copy(agent.state.rotation)

        # get the current pose of the agent
        x, y, heading = position.x, position.y, rotation.z
        state.pose = (x, y, heading)

        # get the desired action of the agent
        move_by = action[0]
        turn_by = math.degrees(action[1])

        # set animation speed
        # TODO: move constants into constants.py
        self.set_animation(agent, state, 'run')
        delay = OpenNero.getSimContext().delay
        if delay > 0.0: # if there is a need to show animation
            agent.state.animation_speed = move_by * 28.0 / delay

        # figure out the new heading
        new_heading = common.wrap_degrees(heading, turn_by)

        # figure out the new x, y location
        new_x = x + constants.MAX_MOVEMENT_SPEED * math.cos(math.radians(new_heading)) * move_by
        new_y = y + constants.MAX_MOVEMENT_SPEED * math.sin(math.radians(new_heading)) * move_by

        # figure out the firing location
        fire_x = x + self.MAX_DIST * math.cos(math.radians(new_heading))
        fire_y = y + self.MAX_DIST * math.sin(math.radians(new_heading))

        # draw the line of fire
        fire_pos = copy.copy(position)
        fire_pos.x, fire_pos.y = fire_x, fire_y

        # calculate if we hit anyone
        hit = 0
        data = self.target(agent)
        if data != None:#len(data) > 0:
            objects = OpenNero.getSimContext().findInRay(position, data.state.position, constants.OBJECT_TYPE_OBSTACLE | constants.OBJECT_TYPE_TEAM_0 | constants.OBJECT_TYPE_TEAM_1, True)
            if len(objects) > 0: sim = objects[0]
            else: sim = data
            if len(objects) == 0 or objects[0] == sim:
                target = self.get_state(data)
                if target != -1:
                    target.curr_damage += 1
                    hit = 1

        # calculate friend/foe
        friends, foes = self.getFriendFoe(agent)
        if not friends:
            return reward #Corner Case

        friend = self.nearest(state.pose, state.id, friends)
        foe = self.nearest(state.pose, state.id, foes)

        #calculate fitness accrued during this step
        R = dict([(f, 0) for f in constants.FITNESS_DIMENSIONS])
        R[constants.FITNESS_STAND_GROUND] = -action[0]
        if friend:
            d = self.distance(self.get_state(friend).pose, state.pose)
            R[constants.FITNESS_STICK_TOGETHER] = -d*d
        if foe:
            d = self.distance(self.get_state(foe).pose, state.pose)
            R[constants.FITNESS_APPROACH_ENEMY] = -d*d
        d = self.flag_distance(agent)
        R[constants.FITNESS_APPROACH_FLAG] = -d*d
        R[constants.FITNESS_HIT_TARGET] = hit
        R[constants.FITNESS_AVOID_FIRE] = -damage

        # put the fitness dimensions into the reward vector in order
        for i, f in enumerate(constants.FITNESS_DIMENSIONS):
            reward[i] = R[f]

        # tell the system to make the calculated motion
        state.prev_pose = state.pose
        state.pose = (new_x, new_y, new_heading)

        # try to update position
        pos = copy.copy(agent.state.position)
        pos.x = new_x
        pos.y = new_y
        agent.state.position = pos

        # try to update rotation
        rot = copy.copy(agent.state.rotation)
        rot.z = new_heading
        agent.state.rotation = rot

        return reward

    def sense(self, agent, observations):
        """
        figure out what the agent should sense
        """
        state = self.get_state(agent)
        x, y, _ = state.pose
        friends, foes = self.getFriendFoe(agent)
        if not friends:
            return v
        for f in friends:
            x += friends[f].pose[0]
            y += friends[f].pose[1]
        x /= len(friends)
        y /= len(friends)
        fd = self.distance(state.pose, (x, y))
        fh = 0
        if fd != 0:
            fh = ((math.degrees(math.atan2(y - state.pose[1], x - state.pose[0])) - state.pose[2]) % 360) - 180
        if fd <= 15:
            observations[-3] = fd / 15.0
            observations[-2] = fh / 360.0
        if observations[-2] < 0:
            observations[-2] += 1
        observations[-1] = int(self.target(agent) is not None)
        return observations

    def flag_distance(self, agent):
        """
        Returns the distance of the current agent from the flag
        """
        f = module.getMod().flag_loc
        return self.distance(self.get_state(agent).pose, (f.x, f.y))

    def distance(self, a, b):
        """
        Returns the distance between positions (x-y tuples) a and b.
        """
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def nearest(self, loc, id, agents):
        """
        Returns the nearest agent in a list of agents to an agent with a
        given id at a given location.
        """
        # TODO: this needs to only be computed once per tick, not per agent
        nearest = None
        min_dist = self.MAX_DIST * 5
        for a in agents:
            if id == agents[a].id:
                continue
            d = self.distance(loc, agents[a].pose)
            if d < min_dist:
                nearest = a
                min_dist = d
        return nearest

    def set_animation(self, agent, state, animation):
        """
        Sets current animation
        """
        if agent.state.animation != animation:
            agent.state.animation = animation

    def is_episode_over(self, agent):
        """
        is the current episode over for the agent?
        """
        if agent.group == "Turret": return False
        self.max_steps = module.getMod().lt
        state = self.get_state(agent)
        if self.max_steps != 0 and agent.step >= self.max_steps:
            return True
        if not OpenNero.get_ai("rtneat").has_organism(agent):
            return True
        if module.getMod().hp != 0 and state.total_damage >= module.getMod().hp:
            return True
        else:
            return False

    def cleanup(self):
        """
        cleanup the world
        """
        common.killScript('NERO/menu.py')
        return True
