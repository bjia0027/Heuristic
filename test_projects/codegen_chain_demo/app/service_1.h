#pragma once
#include <functional>
#include <vector>

class Service1 {
public:
    Service1();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
