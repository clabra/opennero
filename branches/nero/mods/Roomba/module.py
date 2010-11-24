# load standard libraries #
import random
import time
from math import *

# load C-side code #
from OpenNero import *

# load Python functional scripts #
from common import *
import world_handler
from agent_handler import AgentState, AgentInit

# load agent script
from roomba import RoombaBrain
from RTNEATAgent import RTNEATAgent

# initialize global variables #
MAX_SPEED = 1
STEP_DT = 0.1
AGENT_X = 10
AGENT_Y = 10

ROOMBA_RAD = 4  # Physical Radius of Roomba, for wall collision

N_FIXED_SENSORS = 3     # 0: wall bump, 1: self position X, 2: self position Y
N_S_IN_BLOCK = 4

XDIM = 200.0
YDIM = 200.0
HEIGHT = 20.0
OFFSET = -HEIGHT/2

class SandboxMod:

    def __init__(self):
        """
        initialize the sandbox server
        """
        self.marker_map = {} # a map of cells and markers so that we don't have more than one per cell
        self.environment = None
        self.agent_ids = []
    
    def mark(self, x, y, marker):
        """ Mark a position (x, y) with the specified color """
        # remove the previous object, if necessary
        self.unmark(x, y)
        # remember the ID of the object we are about to create
        self.marker_map[(x, y)] = getNextFreeId()
        # add a new marker object
        addObject(marker, Vector3f(x, y, -1), Vector3f(0,0,0), Vector3f(0.5,0.5,0.5))
	    
    def mark_blue(self, x, y):
        self.mark(x, y,"data/shapes/cube/BlueCube.xml")
    
    def mark_green(self, x, y):
        self.mark(x, y,"data/shapes/cube/GreenCube.xml")
    
    def mark_yellow(self, x, y):
        self.mark(x, y,"data/shapes/cube/YellowCube.xml")
    
    def mark_white(self, x, y):
        self.mark(x, y,"data/shapes/cube/WhiteCube.xml")
    
    def unmark(self, x, y):
        if (x, y) in self.marker_map:
            removeObject(self.marker_map[(x, y)])
            del self.marker_map[(x, y)]
            return True
        else:
            return False
    
    def setup_sandbox(self):
        """
        setup the sandbox environment
        """
        global XDIM, YDIM, HEIGHT, OFFSET
        self.environment = SandboxEnvironment(XDIM, YDIM)
        set_environment(self.environment)
    
    def reset_sandbox(self=None):
        """
        reset the sandbox and refill with stuff to vacuum
        """
        for id in self.marker_map.values():
            removeObject(id)  # delete id from Registry, not from dict
        self.marker_map = {}
        for id in self.agent_ids:
            removeObject(id)  # delete id from Registry, not from list
        self.agent_ids = []
        reset_ai()

    def remove_bots(self):
        """ remove all existing bots from the environment """
        disable_ai()
        for id in self.agent_ids:
            removeObject(id)  # delete id from Registry, not from list
        self.agent_ids = []

    def add_bots(self, bot_type, num_bots):
        disable_ai()
        num_bots = int(num_bots)
        if bot_type.lower().find("script") >= 0:
            for i in range(0, num_bots):
                agent_id = getNextFreeId()
                self.agent_ids.append(agent_id)
                addObject("data/shapes/roomba/Roomba.xml", Vector3f(random.random()*XDIM, random.random()*YDIM,0), Vector3f(0.5, 0.5, 0.5))
            enable_ai()
            return True
        elif bot_type.lower().find("rtneat") >= 0:
            self.start_rtneat(num_bots)
            return True
        elif bot_type.lower().find("asuka") >= 0:
            self.agent_ids.append(getNextFreeId())
            addObject("data/ai/Asuka.xml", Vector3f(XDIM/2,YDIM/2,0))
            enable_ai()
            return True
        else:
            return False

    def start_rtneat(self, pop_size):
        " start the rtneat learning demo "
        disable_ai()
        #self.environment = SandboxEnvironment(XDIM, YDIM, self)
        #set_environment(self.environment)
        #self.reset_sandbox()
        # Create RTNEAT object
        rtneat = RTNEAT("data/ai/neat-params.dat", 6, 2, pop_size, 1.0)
        set_ai("neat",rtneat) 
        enable_ai()
        for i in range(0, pop_size):
            self.agent_ids.append(getNextFreeId())
            addObject("data/shapes/roomba/RoombaRTNEAT.xml", Vector3f(random.random()*XDIM, random.random()*YDIM,0) )
        

#################################################################################        
class SandboxEnvironment(Environment):
    SPEED = 10 # max per-step translational speed
    ANGULAR_SPEED = 90 # max angles in degrees agent can turn in one step
    TIME_PER_STEP = 0.01 # min time between steps in seconds
    STEPS_PER_EPISODE = 100 # max number of steps per episode
    MAX_DISTANCE = 1000000 # max possible distance of objects from agent
    MIN_DISTANCE = 1 # min distance from object for agent to visit it

    """
    Sample Environment for the Sandbox
    """
    def __init__(self, XDIM, YDIM):
        """
        Create the environment
        """
        Environment.__init__(self) 
        
        self.XDIM = XDIM
        self.YDIM = YDIM
        self.max_steps = 500       
        self.crumb_count = 0
        self.states = {} # dictionary of agent states
        self.crumbs = world_handler.pattern_cluster(500, "Roomba/world_config.txt")

        self.init_list = AgentInit()
        self.init_list.add_type("<class 'Roomba.roomba.RoombaBrain'>")
        self.init_list.add_type("<class 'Roomba.RTNEATAgent.RTNEATAgent'>")
        #print self.init_list.types

        roomba_abound = self.init_list.get_action("<class 'Roomba.roomba.RoombaBrain'>")
        roomba_sbound = self.init_list.get_sensor("<class 'Roomba.roomba.RoombaBrain'>")
        roomba_rbound = self.init_list.get_reward("<class 'Roomba.roomba.RoombaBrain'>")
        rtneat_abound = self.init_list.get_action("<class 'Roomba.RTNEATAgent.RTNEATAgent'>")
        rtneat_sbound = self.init_list.get_sensor("<class 'Roomba.RTNEATAgent.RTNEATAgent'>")
        rtneat_rbound = self.init_list.get_reward("<class 'Roomba.RTNEATAgent.RTNEATAgent'>")

        ### Bounds for Roomba ###
        # actions
        roomba_abound.add_continuous(-pi, pi) # amount to turn by
        
        # sensors
        roomba_sbound.add_discrete(0,1)    # wall bump
        roomba_sbound.add_continuous(0,XDIM)   # position X
        roomba_sbound.add_continuous(0,YDIM)   # position Y
        
        # rewards
        roomba_rbound.add_continuous(-100,100) # range for reward

        ### End Bounds for Roomba ####

        ### Bounds for RTNEAT ###
        # actions
        rtneat_abound.add_continuous(-0.5, 0.5)
        rtneat_abound.add_continuous(-0.5, 0.5)
        
        # sensors
        rtneat_sbound.add_continuous(-1, 1)
        rtneat_sbound.add_continuous(-1, 1)
        rtneat_sbound.add_continuous(-1, 1)
        rtneat_sbound.add_continuous(-1, 1)
        rtneat_sbound.add_continuous(-1, 1)
        rtneat_sbound.add_continuous(-1, 1)
    
        # rewards
        rtneat_rbound.add_continuous(-1, 1)
        ### End Bounds for RTNEAT ###

        # set up shop
        # Add Wayne's Roomba room with experimentally-derived vertical offset to match crumbs.
        addObject("data/terrain/RoombaRoom.xml", Vector3f(XDIM/2,YDIM/2, -1), Vector3f(0,0,0), Vector3f(XDIM/245.0, YDIM/245.0, HEIGHT/24.5))

        # getSimContext().addAxes()
        self.add_crumbs()
        for crumb in self.crumbs:
            self.add_crumb_sensors(roomba_sbound)        

    def get_state(self, agent):
        if agent in self.states:
            return self.states[agent]
        else:
            print "new state created"
            pos = agent.state.position
            rot = agent.state.rotation
            self.states[agent] = AgentState(pos, rot)
            return self.states[agent]
        
    def randomize(self):
        self.crumbs = world_handler.read_pellets()

    def add_crumb_sensors(self, roomba_sbound):
        """Add the crumb sensors, in order: x position of crumb (0 to XDIM,
        continuous), y position of crumb (0 to XDIM, continuous), whether
        crumb is present at said position or has been vacced (0 or 1), and
        reward for vaccing said crumb."""
        roomba_sbound.add_continuous(0, XDIM)    # crumb position X
        roomba_sbound.add_continuous(0, YDIM)    # crumb position Y
        roomba_sbound.add_discrete(0, 1)       # crumb present/ not present
        roomba_sbound.add_discrete(1, 5)       # reward for crumb

    def add_crumbs(self):
        for pellet in self.crumbs:
            if not (pellet.x, pellet.y) in getMod().marker_map:
                getMod().mark_blue(pellet.x, pellet.y)
        self.crumb_count = len(getMod().marker_map)

    def reset(self, agent):
        """ reset the environment to its initial state """
        state = self.get_state(agent)
        state.reset()
        agent.state.position = state.initial_position
        agent.state.rotation = state.initial_rotation
        agent.state.velocity = state.initial_velocity
        state.episode_count += 1
        self.add_crumbs()
        print "Episode %d complete" % state.episode_count
        return True

    def get_agent_info(self, agent):
        """ return a blueprint for a new agent """
        return self.init_list.get_info(str(type(agent)))

    def num_sensors(self):
        return (len(getMod().marker_map)*4 + N_FIXED_SENSORS)
    
    def step(self, agent, action):
        """
        A step for an agent
        """
        state = self.get_state(agent) # the agent's status
        if (state.is_out == True):
            getMod().unmark(agent.state.position.x, agent.state.position.y)
        else:
            assert(self.get_agent_info(agent).actions.validate(action)) # check if the action is valid
            if (str(type(agent)) == "<class 'Roomba.roomba.RoombaBrain'>"):
                angle = action[0] # in range of -pi to pi
                degree_angle = degrees(angle)
                delta_angle = degree_angle - agent.state.rotation.z
                delta_dist = MAX_SPEED
            else:
                # The first action specifies the distance to move in the forward direction
                # and the second action specifies the angular change in the orientation of
                # the agent.
                delta_dist = action[0]*self.SPEED
                delta_angle = action[1]*self.ANGULAR_SPEED
            reward = self.update_position(agent, delta_dist, delta_angle)
        state.reward += reward
        return reward

    # delta_angle (degrees) is change in angle
    # delta_dist is change in distance (or velocity, since unit of time unchanged)
    def update_position(self, agent, delta_dist, delta_angle):
        state = self.get_state(agent)
        state.step_count += 1

        position = agent.state.position
        rotation = agent.state.rotation

        # posteriori collision detection
        rotation.z += delta_angle
        position.x += delta_dist*cos(radians(rotation.z))
        position.y += delta_dist*sin(radians(rotation.z))

        # check if one of 4 out-of-bound conditions applies
        # if yes, back-track to correct position
        if (position.x) < 0 or (position.y) < 0 or \
           (position.x) > self.XDIM or (position.y) > self.YDIM:

            print "bump @ ", position.x, ", ", position.y
            # correct position
            if (position.x) < 0:
                position.x -= delta_dist*cos(radians(rotation.z))    
            if (position.y) < 0:
                position.y -= delta_dist*sin(radians(rotation.z))
            if (position.x) > self.XDIM:
                position.x -= delta_dist*cos(radians(rotation.z))
            if (position.y) > self.YDIM:
                position.y -= delta_dist*sin(radians(rotation.z))
            
        # register new position
        state.position = position
        state.rotation = rotation
        agent.state.position = position
        agent.state.rotation = rotation
        
        reward = 0
        
        for pellet in self.crumbs:
            if ((pellet.x, pellet.y) in getMod().marker_map):
                dist = sqrt((pellet.x - position.x)**2 + (pellet.y - position.y)**2)
                if (dist <= 4):  # if agent gets close enough to a crumb
                    getMod().unmark(pellet.x, pellet.y)
                    self.crumb_count -= 1  # decrement crumb count
                    if (self.crumb_count <= 0):  # final Reward (no crumb left behind)
                        if  (self.max_steps != 0):  # for yes step limit
                            reward += pellet.reward + self.max_steps - state.step_count
                        else:                       # for no step limit
                            reward += pellet.reward + (1/agent.state_count) * 10000
                    else:
                        reward += pellet.reward     # normal reward for picking up a pellet
                
        # check if agent has expended its step allowance
        if (self.max_steps != 0) and (state.step_count >= self.max_steps):
            state.is_out = True    # if yes, mark it to be removed
        return reward            
    
    def sense(self, agent):
        """ figure out what the agent should sense """
        sensors = self.get_agent_info(agent).sensors.get_instance()
        state = self.get_state(agent)
        if (str(type(agent)) == "<class 'Roomba.roomba.RoombaBrain'>"):
            if state.bumped:
                sensors[0] = 1
                state.bumped = False
            else:
                sensors[0] = 0

            # get agent's position
            pos = agent.state.position
            sensors[1] = pos.x
            sensors[2] = pos.y
        
            self.sense_crumbs(sensors, N_S_IN_BLOCK, N_FIXED_SENSORS)

        else:
            """ Copied over from creativeit branch """
            sensors[0] = self.MAX_DISTANCE
            sensors[1] = self.MAX_DISTANCE
            sensors[2] = self.MAX_DISTANCE
            sensors[3] = self.MAX_DISTANCE
            sensors[4] = -1
            sensors[5] = self.MAX_DISTANCE
            
            # The first four sensors detect the distance to the nearest cube in each of the
            # four quadrants defined by the coordinate frame attached to the agent.  The
            # positive X axis of the coordinate frame is oriented in the forward direction
            # with respect to the agent.  The fifth sensor detects the minimum angular
            # distance between the agent and the nearest cubes detected by the other sensors.
            # All sensor readings are normalized to lie in [-1, 1].
            
            for cube_position in getMod().marker_map:
                
                distx = cube_position[0] - agent.state.position.x
                disty = cube_position[1] - agent.state.position.y
                dist = sqrt(distx**2 + disty**2)
                angle = degrees(atan2(disty, distx)) - agent.state.rotation.z  # range [-360, 360]
                if angle > 180: angle = angle - 360
                if angle < -180: angle = angle + 360
                angle = angle/180 # range [-1, 1]
                if angle >= -1 and angle < -0.5:
                    if dist < sensors[0]:
                        sensors[0] = dist
                        if fabs(angle) < fabs(sensors[4]): sensors[4] = angle
                elif angle >= -0.5 and angle < 0:
                    if dist < sensors[1]:
                        sensors[1] = dist
                        if fabs(angle) < fabs(sensors[4]): sensors[4] = angle
                elif angle >= 0 and angle < 0.5:
                    if dist < sensors[2]:
                        sensors[2] = dist
                        if fabs(angle) < fabs(sensors[4]): sensors[4] = angle
                else:
                    if dist < sensors[3]:
                        sensors[3] = dist
                        if fabs(angle) < fabs(sensors[4]): sensors[4] = angle
                                
            # Any distance sensor that still has the value MAX_DISTANCE is set to -1.
            for i in range(0, 6):
                if i != 4 and sensors[i] >= self.MAX_DISTANCE:
                    sensors[i] = -1

            # Invert and normalize the remaining distance sensor values to [0, 1]
            maxval = max(sensors[0], sensors[1], sensors[2], sensors[3], sensors[5])
            if maxval > 0:
                for i in range(0, 6):
                    if i != 4 and sensors[i] > 0:
                        sensors[i] = 1 - (sensors[i]/maxval)

            # Now, sensors that do not detect any cubes/wall will have the value -1,
            # sensors that detect cubes/wall at maxval distance will have the value 0,
            # and sensors that detect cubes/wall at zero distance will have value 1.
        return sensors

    def sense_crumbs(self, sensors, num_sensors, start_sensor):
        i = start_sensor
        for pellet in self.crumbs:
            sensors[i] = pellet.x
            sensors[i+1] = pellet.y
            if (pellet.x, pellet.y) in getMod().marker_map:
                sensors[i+2] = 1
            else:
                sensors[i+2] = 0 
            sensors[i+3] = pellet.reward
            i = i + num_sensors
        return True
                     
    def is_active(self, agent):
        """ return true when the agent should act """
        state = self.get_state(agent)
        if time.time() - state.time > STEP_DT:
            state.time = time.time()
            return True
        else:
            return False     
    
    def is_episode_over(self, agent):
        """ is the current episode over for the agent? """
        state = self.get_state(agent)
        if self.max_steps != 0 and state.step_count >= self.max_steps:
            return True
        elif (self.crumb_count <= 0):
            return True
        else:
            return False
    
    def cleanup(self):
        """
        cleanup the world
        """
        self.environment = None
        return True

gMod = None

def delMod():
    global gMod
    gMod = None

def getMod():
    global gMod
    if not gMod:
        gMod = SandboxMod()
    return gMod

def ServerMain():
    print "Starting Sandbox Environment"