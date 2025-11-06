#pragma once
#include "service_39.h"
#include "model_39.h"
#include <memory>

class Controller39 {
public:
    Controller39();
    void initialize();
    void run();
private:
    std::unique_ptr<Service39> service_;
    std::shared_ptr<Model39> model_;
};
