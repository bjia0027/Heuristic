#pragma once
#include "service_33.h"
#include "model_33.h"
#include <memory>

class Controller33 {
public:
    Controller33();
    void initialize();
    void run();
private:
    std::unique_ptr<Service33> service_;
    std::shared_ptr<Model33> model_;
};
