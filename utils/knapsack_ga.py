"""
PanPipe package
Copyright 2019,2020 Daniel Ortiz-Mart\'inez
 
This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public License
as published by the Free Software Foundation; either version 3
of the License, or (at your option) any later version.
 
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.
 
You should have received a copy of the GNU Lesser General Public License
along with this program; If not, see <http://www.gnu.org/licenses/>.
"""
 
# *- python -*

# import modules
import random, time

##############################################################################
# 0-1 Knapsack Problem solved using Genetic Algorithms
#
# Based on github code created by Edmilson Rocha
# GitHub: https://github.com/edmilsonrobson
##############################################################################
        
##################################################
def fitness(target,weights,values,capacities):
    """
    fitness(target) will return the fitness value of permutation named "target".
    Higher scores are better and are equal to the total value of items in the permutation.
    If total_weight is higher than the capacities, return 0 because the permutation cannot be used.
    """
    total_value = 0
    total_weights = []
    for i in range(len(weights)):
        total_weights.append(0)
        
    # Compute total value
    for i in range(len(target)):
        if (target[i]==1):
            total_value+=values[i]

    # Compute weights
    for i in range(len(weights)):
        for j in range(len(weights[i])):
            if (target[j]==1):
                total_weights[i]+=weights[i][j]        

    # Verify capacities
    excess=0
    for i in range(len(total_weights)):
        if total_weights[i] > capacities[i]:
            # Capacity exceeded, accumulate excess
            capacity_exceeded=True
            excess+=total_weights[i] - capacities[i]

    # Return value
    if excess==0:
        return total_value
    else:
        return -excess
    
##################################################
def spawn_starting_population(amount,start_pop_with_zeroes,num_items):
    population=[]
    for x in range (0,amount):
        population.append(spawn_individual(start_pop_with_zeroes,num_items))
    return population

##################################################
def spawn_individual(start_pop_with_zeroes,num_items):
    if start_pop_with_zeroes:
        individual=[]
        for x in range (0,num_items):
            individual.append(random.randint(0,0))
        return individual
    else:
        individual=[]
        for x in range (0,num_items):
            individual.append(random.randint(0,1))
        return individual

##################################################
def mutate(target):
    """
    Changes a random element of the permutation array from 0 -> 1 or from 1 -> 0.
    """ 
    r = random.randint(0,len(target)-1)
    if target[r] == 1:
        target[r] = 0
    else:
        target[r] = 1

##################################################
def evolve_population(pop):
    # Define evolve parameters
    parent_eligibility = 0.2
    mutation_chance = 0.1
    parent_lottery = 0.05

    # Determine parents list as the n-best fitted individuals
    # (n=parent_eligibility*len(pop))
    parent_length = int(parent_eligibility*len(pop))
    parents = pop[:parent_length]
    nonparents = pop[parent_length:]

    # Add a small fraction of less fitted individuals to the parent set
    for np in nonparents:
        if parent_lottery > random.random():
            parents.append(np)

    # Mutation lottery
    for p in parents:
        if mutation_chance > random.random():
            mutate(p)

    # Start breeding
    children = []
    desired_length = len(pop) - len(parents)
    while len(children) < desired_length :
        male = pop[random.randint(0,len(parents)-1)]
        female = pop[random.randint(0,len(parents)-1)]        
        mixpoint=random.randint(0,len(parents))
        child = male[:mixpoint] + female[mixpoint:] # from start to mixpoint from father, from mixpoint to end from mother
        if mutation_chance > random.random():
            mutate(child)
        children.append(child)

    # Add children to parents list
    parents.extend(children)

    return parents

##################################################
def get_packed_items(chrom):
    packed_items=[]
    for i in range(len(chrom)):
        if chrom[i]==1:
            packed_items.append(i)
    return packed_items
            
##################################################
def knapsack_solve(max_gen,pop_size,start_pop_with_zeroes,weights,values,capacities,time_limit=-1):
    # Set random number seed
    random.seed(31415)

    # Get start time
    start=time.clock()
    
    # Compute generations
    generation = 1
    population = spawn_starting_population(pop_size,start_pop_with_zeroes,len(values))
    for g in range(max_gen):
        population = sorted(population, key=lambda x: fitness(x,weights,values,capacities), reverse=True)
        population = evolve_population(population)
        generation += 1
        curr=time.clock()-start
        if time_limit > 0 and curr > time_limit:
            break

    # Sort final population
    population = sorted(population, key=lambda x: fitness(x,weights,values,capacities), reverse=True)
    
    # Obtain solution
    best_fitted_chrom=population[0]
    computed_value=fitness(best_fitted_chrom,weights,values,capacities)
    packed_items=get_packed_items(best_fitted_chrom)
    
    return computed_value,packed_items
