import time
from math import *
from OpenNero import *
from NERO.module import *
from constants import *
from copy import copy
from random import *
import sys

class AgentState:
    """
    State that we keep for each agent
    """
    def __init__(self):
        self.id = -1
        # current x, y, heading pose
        self.pose = (0, 0, 0)
        # previous x, y, heading pose
        self.prev_pose = (0, 0, 0)
        # starting position
        self.initial_position = Vector3f(0, 0, 0)
        # starting orientation
        self.initial_rotation = Vector3f(0, 0, 0)        
        self.time = time.time()
        self.start_time = self.time
        self.total_damage = 0
        self.curr_damage = 0
        self.animation = 'stand'

class NeroEnvironment(Environment):
    """
    Environment for the Nero
    """
    def __init__(self):
        from NERO.module import getMod
        """
        Create the environment
        """
        Environment.__init__(self) 
        
        self.curr_id = 0
        self.step_delay = 0.25 # time between steps in seconds
        self.max_steps = 20
        self.time = time.time()
        self.MAX_DIST = pow((pow(XDIM, 2) + pow(YDIM, 2)), .5)
        self.states = {}
        self.teams = {}
        self.speedup = 0
        
        abound = FeatureVectorInfo() # actions
        sbound = FeatureVectorInfo() # sensors
        rbound = FeatureVectorInfo() # rewards
        
        # actions
        abound.add_continuous(-1,1) # forward/backward speed
        abound.add_continuous(-0.2, 0.2) # left/right turn (in radians)

        # Wall sensors
        for a in WALL_SENSORS:
            sbound.add_continuous(0,1)
                
        # Flag sensors
        for fs in FLAG_SENSORS:
            sbound.add_continuous(0,1)
        
        # Enemy sensors
        for es in ENEMY_SENSORS:
            sbound.add_continuous(0,1)

        # Friend Sensors
        sbound.add_continuous(0,1)
        sbound.add_continuous(0,1)
        sbound.add_continuous(0,1)

        # Rewards
        # the enviroment returns the raw multiple dimensions of the fitness as
        # they get each step. This then gets combined into, e.g. Z-score, by
        # the ScoreHelper in order to calculate the final rtNEAT-fitness
        for f in FITNESS_DIMENSIONS:
            # we don't care about the bounds of the individual dimensions
            rbound.add_continuous(-sys.float_info.max, sys.float_info.max) # range for reward
        
        # initialize the rtNEAT algorithm parameters
        # input layer has enough nodes for all the observations plus a bias
        # output layer has enough values for all the actions
        # population size matches ours
        # 1.0 is the weight initialization noise
        rtneat = RTNEAT("data/ai/neat-params.dat", NEAT_SENSORS + 1, NEAT_ACTIONS, pop_size, 1.0, rbound)
        
        set_ai("rtneat", rtneat)
        
        self.agent_info = AgentInitInfo(sbound, abound, rbound)
    
    def reset(self, agent):
        """
        reset the environment to its initial state
        """
        from NERO.module import getMod
        state = self.get_state(agent)
        if agent.group == "Agent":
            dx = randrange(XDIM/20) - XDIM/40
            dy = randrange(XDIM/20) - XDIM/40
            state.initial_position.x = getMod().spawn_x + dx
            state.initial_position.y = getMod().spawn_y + dy
            agent.state.position = copy(state.initial_position)
            agent.state.rotation = copy(state.initial_rotation)
            state.pose = (state.initial_position.x, state.initial_position.y, state.initial_rotation.z)
            state.prev_pose = state.pose
        state.total_damage = 0
        state.curr_damage = 0
        ff = self.getFriendFoe(agent)
        return True
    
    def get_agent_info(self, agent):
        """
        return a blueprint for a new agent
        """ 
        for a in WALL_SENSORS:
            agent.add_sensor(RaySensor(cos(radians(a)), sin(radians(a)), 0, MAX_VISION_RADIUS, OBJECT_TYPE_OBSTACLE))
        for (a0, a1) in FLAG_SENSORS:
            agent.add_sensor(RadarSensor(a0, a1, -90, 90, MAX_VISION_RADIUS * 5, OBJECT_TYPE_FLAG))
        for (a0, a1) in ENEMY_SENSORS:
            if agent.get_team() == 0: agent.add_sensor(RadarSensor(a0, a1, -90, 90, MAX_VISION_RADIUS * 5, OBJECT_TYPE_TEAM_1))
            if agent.get_team() == 1: agent.add_sensor(RadarSensor(a0, a1, -90, 90, MAX_VISION_RADIUS * 5, OBJECT_TYPE_TEAM_0))
        return self.agent_info
   
    def get_state(self, agent):
        """
        Returns the state of an agent
        """
        if agent in self.states:
            return self.states[agent]
        else:
            self.states[agent] = AgentState()
            self.states[agent].id = agent.state.id
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
        return (friend, foe)

    def target(self, agent):
        #Get list of all targets
        ffr = self.getFriendFoe(agent)
        alt = ffr[1]#ffr[0] + ffr[1]
        if (ffr[0] == []):
            return None


        state = self.get_state(agent)
        
        #sort in order of variance from 0~2 degrees (maybe more)
        valids = []
        for curr in alt:
            fd = self.distance(state.pose,(alt[curr].pose[0],alt[curr].pose[1]))
            if fd != 0:
                fh  = ((degrees(atan2(alt[curr].pose[1]-state.pose[1],alt[curr].pose[0] - state.pose[0])) - state.pose[2]) % 360)
            else:
                fh = 0
            fh = abs(fh)
            if fh <= 2:
                valids.append((curr,fd,fh))
             
        #Valids contains (state,distance,heading to distance) pairs
        #get one that is nearest based on distance / cos(radians(degrees() * 20))
        top = None 
        top_v = 'A'

        for (curr,fd,fh) in valids:
            if top_v == 'A' or top_v > (fd / cos(radians(fh * 20))):
                top = curr
                top_v = (fd/cos(radians(fh * 20)))

        return top

    def step(self, agent, action):
        """
        2A step for an agent
        """
        from NERO.module import getMod, parseInput
        # check if the action is valid
        assert(self.agent_info.actions.validate(action))
        
        state = self.get_state(agent)
        
        # get the reward (which has multiple components)
        reward = self.agent_info.reward.get_instance()

        #Initilize Agent state
        if agent.step == 0:
            p = agent.state.position
            r = agent.state.rotation
            if agent.group == "Agent":
                r.z = randrange(360)
                agent.state.rotation = r #Note the internal components of agent.state.rotation are immutable you need to make a copy, modify the copy, and set agent.state.rotation to be the copy.
            state.initial_position = p
            state.initial_rotation = r
            state.pose = (p.x, p.y, r.z)
            state.prev_pose = (p.x, p.y, r.z)
            return reward
        
        # Spawn more agents if there are more to spawn
        if get_ai("rtneat").ready():
            if getMod().getNumToAdd() > 0:
                dx = randrange(XDIM/20) - XDIM/40
                dy = randrange(XDIM/20) - XDIM/40
                getMod().addAgent((getMod().spawn_x + dx, getMod().spawn_y + dy, 2))

        # Update Damage totals
        state.total_damage += state.curr_damage
        damage = state.curr_damage
        state.curr_damage = 0
        
        #Fitness Function Parameters
        distance_st = getMod().dta
        distance_ae = getMod().dtb
        distance_af = getMod().dtc
        friendly_fire = getMod().ff

        # the position and the rotation of the agent on-screen
        position = agent.state.position
        rotation = agent.state.rotation
        
        # get the current pose of the agent
        (x, y, heading) = state.pose
        
        # get the actions of the agent
        move_by = action[0]
        turn_by = degrees(action[1])
        
        # figure out the new heading
        new_heading = wrap_degrees(heading, turn_by)
        
        # figure out the new x,y location
        new_x = x + MAX_MOVEMENT_SPEED * cos(radians(new_heading)) * move_by
        new_y = y + MAX_MOVEMENT_SPEED * sin(radians(new_heading)) * move_by
        
        # figure out the firing location
        fire_x = x + self.MAX_DIST * cos(radians(new_heading))
        fire_y = y + self.MAX_DIST * sin(radians(new_heading))

        # draw the line of fire
        fire_pos = copy(position)
        fire_pos.x, fire_pos.y = fire_x, fire_y
        
        # calculate if we hit anyone
        hit = 0
        data = self.target(agent)
        #string = agent.state.label + str(len(data)) + ": "
        if data != None:#len(data) > 0:
                print "We're getting inside at least"
                objects = getSimContext().findInRay(position,data.state.position, OBJECT_TYPE_AGENT & OBJECT_TYPE_OBSTACLE ,True)
                if len(objects) > 0: sim = objects[0]
                else: sim = data
                if len(objects) == 0 or objects[0] == sim:
                 #string += str(sim.label) + "," + str(sim.id) + ";"
                 target = self.get_state(data)
                 print "Target hit successfully pre"
                 if target != -1:
                    target.curr_damage += 1
                    hit = 1
                    print "Target hit successfully"
        
        # calculate friend/foe
        ffr = self.getFriendFoe(agent)
        if ffr[0] == []:
            return reward #Corner Case
        ff = []
        ff.append(self.nearest(state.pose, state.id, ffr[0]))
        ff.append(self.nearest(state.pose, state.id, ffr[1]))

        st = 0
        ae = 0

        #calculate fitness accrued during this step
        R = dict([(f, 0) for f in FITNESS_DIMENSIONS])
        R[FITNESS_STAND_GROUND] = -action[0]
        if ff[0] != 1 and self.distance(ff[0].pose,state.pose) != 0:
            R[FITNESS_STAND_GROUND] = distance_st / self.distance(ff[0].pose,state.pose)
        if ff[1] != 1 and self.distance(ff[1].pose,state.pose) != 0:
            R[FITNESS_APPROACH_ENEMY] = distance_ae / self.distance(ff[1].pose,state.pose)
        R[FITNESS_APPROACH_FLAG] = (distance_af/self.flag_distance(agent))
        R[FITNESS_HIT_TARGET] = hit
        R[FITNESS_AVOID_FIRE] = -damage
        
        # put the fitness dimensions into the reward vector in order
        for (i,f) in enumerate(FITNESS_DIMENSIONS):
            reward[i] = R[f]
        
        # calculate the motion
        new_position = copy(position)
        new_position.x, new_position.y = new_x, new_y
        
        # make the calculated motion
        position.x, position.y = state.pose[0], state.pose[1]
        agent.state.position = position
        rotation.z = new_heading
        agent.state.rotation = rotation
        state.prev_pose = state.pose
        state.pose = (new_position.x, new_position.y, rotation.z)
        state.time = time.time()
        
        return reward

    def sense(self, agent, observations):
        """ 
        figure out what the agent should sense
        """
        # we only use the built-in sensors defined in get_agent_info

        f = len(observations)
        state = self.get_state(agent)


        ffr = self.getFriendFoe(agent)
        if (ffr[0] == []): return v
        xloc = agent.state.position.x
        yloc = agent.state.position.y
        for x in ffr[0]:
            xloc += ffr[0][x].pose[0]
            yloc += ffr[0][x].pose[1]
        xloc /= len(ffr[0])
        yloc /= len(ffr[0])
        fd = self.distance(state.pose,(xloc,yloc))
        fh = 0
        if fd != 0:
            fh = ((degrees(atan2(yloc-state.pose[1],xloc - state.pose[0])) - state.pose[2]) % 360) - 180

        if fd <= 15:
            observations[f-3] = fd/15.0
            observations[f-2] = fh/360.0

        if observations[f-2] < 0: observations[f-2] += 1

        
        data = self.target(agent)
        observations[f-1] = 0
        if data != None: observations[f-1] = 1

        return observations
   
    def flag_loc(self):
        """
        Returns the current location of the flag
        """
        from NERO.module import getMod
        return getMod().flag_loc

    def flag_distance(self, agent):
        """
        Returns the distance of the current agent from the flag
        """
        pos = self.get_state(agent).pose
        return pow(pow(float(pos[0]) - self.flag_loc().x, 2) + pow(float(pos[1]) - self.flag_loc().y, 2), .5)

    def distance(self, agloc, tgloc):
        """
        Returns the distance between agloc and tgloc
        """
        return pow(pow(float(agloc[0] - tgloc[0]), 2) + pow(float(agloc[1] - tgloc[1]), 2), .5)

    def angle(self, agloc, tgloc):
        """
        returns the angle between agloc and tgloc (test before using to make sure it's returning what you think it is)
        """
        if(agloc[1] == tgloc[1]):
            return 0
        (x, y, heading) = agloc
        (xt, yt, ignore) = tgloc
        # angle to target
        theading = atan2(yt - y, xt - x)
        rel_angle_to_target = theading - radians(heading)
        return rel_angle_to_target

    def nearest(self, cloc, id, array):
        """
        Returns the nearest agent in array to agent with id id at current location.
        """
        # TODO: this needs to only be computed once per tick, not per agent
        nearest = 1
        value = self.MAX_DIST * 5
        for other in array:
            if id == array[other].id:
                continue
            if self.distance(cloc, array[other].pose) < value:
                nearest = other
                value - self.distance(cloc, array[other].pose)
        return nearest

    def set_animation(self, agent, state, animation):
        """
        Sets current animation
        """
        if state.animation != animation:
            agent.state.setAnimation(animation)
            state.animation = animation
    
    def is_active(self, agent):
        """ return true when the agent should act """
        state = self.get_state(agent)
        # interpolate between prev_pose and pose
        (x1, y1, h1) = state.prev_pose
        (x2, y2, h2) = state.pose
        if x1 != x2 or y1 != y2:
            fraction = 1.0
            if self.get_delay() != 0:
                fraction = min(1.0, float(time.time() - state.time) / self.get_delay())
            pos = agent.state.position
            pos.x = x1 * (1 - fraction) + x2 * fraction
            pos.y = y1 * (1 - fraction) + y2 * fraction
            agent.state.position = pos
            self.set_animation(agent, state, 'run')
        else:
            self.set_animation(agent, state, 'stand')
        if time.time() - state.time > self.get_delay():
            state.time = time.time()
            return True
        else:
            return False
    
    def is_episode_over(self, agent):
        """
        is the current episode over for the agent?
        """
        from NERO.module import getMod
        self.max_steps = getMod().lt
        state = self.get_state(agent)
        if self.max_steps != 0 and agent.step >= self.max_steps:
            return True
        if getMod().hp != 0 and state.total_damage >= getMod().hp:
            return True
        else:
            return False
    
    def cleanup(self):
        """
        cleanup the world
        """
        killScript('NERO/menu.py')
        return True

    def get_delay(self):
        """
        Set simulation delay
        """
        return self.step_delay * (1.0 - self.speedup)