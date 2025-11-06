#pragma once
#include "service_23.h"
#include "model_23.h"
#include <memory>

class Controller23 {
public:
    Controller23();
    void initialize();
    void run();
private:
    std::unique_ptr<Service23> service_;
    std::shared_ptr<Model23> model_;
};
